"""
Subscription & Payment Service
Handles Telegram Stars payments and subscription management
"""
import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Constants
SUBSCRIPTION_PRICE_STARS = 200  # ~$2.00 (100 stars ≈ $1)
SUBSCRIPTION_PRICE_USD = 2.00
SUBSCRIPTION_DURATION_DAYS = 30
REFERRAL_REWARD_PERCENT = 0.30  # 30% від підписки = $0.60
BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")


class SubscriptionService:
    """Subscription management service"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's current subscription"""
        sub = await self.db.subscriptions.find_one(
            {"userId": user_id},
            {"_id": 0}
        )
        return sub
    
    async def is_subscribed(self, user_id: str) -> bool:
        """Check if user has active subscription"""
        sub = await self.get_subscription(user_id)
        if not sub:
            return False
        
        expires_at = sub.get("expiresAt")
        if not expires_at:
            return False
        
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        
        return expires_at > datetime.now(timezone.utc)
    
    async def create_subscription(
        self,
        user_id: str,
        payment_id: str = None,
        duration_days: int = SUBSCRIPTION_DURATION_DAYS
    ) -> Dict[str, Any]:
        """Create or extend subscription"""
        now = datetime.now(timezone.utc)
        
        # Check existing subscription
        existing = await self.get_subscription(user_id)
        
        if existing and existing.get("expiresAt"):
            expires_at = existing["expiresAt"]
            if isinstance(expires_at, str):
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            
            # If active, extend from current expiry
            if expires_at > now:
                new_expiry = expires_at + timedelta(days=duration_days)
            else:
                new_expiry = now + timedelta(days=duration_days)
        else:
            new_expiry = now + timedelta(days=duration_days)
        
        subscription = {
            "userId": user_id,
            "status": "active",
            "plan": "monthly",
            "priceStars": SUBSCRIPTION_PRICE_STARS,
            "startedAt": now,
            "expiresAt": new_expiry,
            "lastPaymentId": payment_id,
            "paymentCount": (existing.get("paymentCount", 0) + 1) if existing else 1,
            "updatedAt": now
        }
        
        await self.db.subscriptions.update_one(
            {"userId": user_id},
            {"$set": subscription, "$setOnInsert": {"createdAt": now}},
            upsert=True
        )
        
        logger.info(f"Subscription created/extended for {user_id} until {new_expiry}")
        
        return {"ok": True, "expiresAt": new_expiry.isoformat(), "subscription": subscription}
    
    async def cancel_subscription(self, user_id: str) -> Dict[str, Any]:
        """Cancel subscription (won't auto-renew)"""
        await self.db.subscriptions.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "status": "cancelled",
                    "cancelledAt": datetime.now(timezone.utc),
                    "updatedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        return {"ok": True, "status": "cancelled"}


class PaymentService:
    """Telegram Stars payment service"""
    
    def __init__(self, db):
        self.db = db
        self.subscription_service = SubscriptionService(db)
    
    async def create_invoice(
        self,
        chat_id: int,
        user_id: str
    ) -> Dict[str, Any]:
        """Create Telegram Stars invoice for subscription"""
        if not BOT_TOKEN:
            logger.error("BOT_TOKEN not set for invoice creation")
            return {"ok": False, "error": "BOT_TOKEN not set"}
        
        invoice_payload = f"sub_{user_id}_{secrets.token_hex(4)}"
        
        logger.info(f"Creating invoice for user {user_id}, chat {chat_id}")
        
        try:
            async with httpx.AsyncClient() as client:
                request_data = {
                    "chat_id": chat_id,
                    "title": "RADAR Premium",
                    "description": "Підписка на місяць - $2.00\n• Доступ до всіх функцій\n• Заробіток на сигналах\n• Реферальна програма 30%",
                    "payload": invoice_payload,
                    "currency": "XTR",  # Telegram Stars
                    "prices": [{"label": "Місячна підписка", "amount": SUBSCRIPTION_PRICE_STARS}],
                    "start_parameter": "subscribe"
                }
                
                logger.info(f"Sending invoice request: {request_data}")
                
                response = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendInvoice",
                    json=request_data,
                    timeout=10.0
                )
                
                data = response.json()
                logger.info(f"Invoice response: {data}")
                
                if data.get("ok"):
                    # Save invoice record
                    invoice = {
                        "invoiceId": invoice_payload,
                        "userId": user_id,
                        "chatId": chat_id,
                        "amount": SUBSCRIPTION_PRICE_STARS,
                        "currency": "XTR",
                        "status": "pending",
                        "createdAt": datetime.now(timezone.utc)
                    }
                    await self.db.invoices.insert_one(invoice)
                    
                    logger.info(f"Invoice created successfully: {invoice_payload}")
                    return {"ok": True, "invoiceId": invoice_payload}
                else:
                    logger.error(f"Invoice creation failed: {data}")
                    return {"ok": False, "error": data.get("description", "Unknown error")}
                    
        except Exception as e:
            logger.error(f"Invoice creation error: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
    
    async def handle_successful_payment(
        self,
        user_id: str,
        chat_id: int,
        payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle successful_payment webhook from Telegram.
        1. Create/extend subscription
        2. Process referral reward
        3. Record payment
        """
        payload = payment_data.get("invoice_payload", "")
        total_amount = payment_data.get("total_amount", SUBSCRIPTION_PRICE_STARS)
        telegram_payment_id = payment_data.get("telegram_payment_charge_id", "")
        
        # Record payment
        payment = {
            "paymentId": f"pay_{secrets.token_hex(8)}",
            "userId": user_id,
            "chatId": chat_id,
            "invoicePayload": payload,
            "telegramPaymentId": telegram_payment_id,
            "amount": total_amount,
            "currency": "XTR",
            "amountUsd": SUBSCRIPTION_PRICE_USD,  # $2.00
            "status": "completed",
            "createdAt": datetime.now(timezone.utc)
        }
        
        await self.db.payments.insert_one(payment)
        
        # Update invoice
        await self.db.invoices.update_one(
            {"invoiceId": payload},
            {"$set": {"status": "paid", "paidAt": datetime.now(timezone.utc)}}
        )
        
        # Create/extend subscription
        sub_result = await self.subscription_service.create_subscription(
            user_id=user_id,
            payment_id=payment["paymentId"]
        )
        
        # Process referral reward (30% = $0.60)
        from .referral_service import ReferralService
        referral_svc = ReferralService(self.db)
        reward_result = await referral_svc.process_payment_reward(
            paying_user_id=user_id,
            payment_amount_usd=SUBSCRIPTION_PRICE_USD
        )
        
        logger.info(f"Payment processed: {user_id} - {total_amount} Stars")
        
        return {
            "ok": True,
            "paymentId": payment["paymentId"],
            "subscription": sub_result,
            "referralReward": reward_result
        }
    
    async def handle_pre_checkout(
        self,
        pre_checkout_query_id: str,
        user_id: str,
        payload: str
    ) -> Dict[str, Any]:
        """Handle pre_checkout_query - validate and approve"""
        if not BOT_TOKEN:
            return {"ok": False, "error": "BOT_TOKEN not set"}
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/answerPreCheckoutQuery",
                    json={
                        "pre_checkout_query_id": pre_checkout_query_id,
                        "ok": True
                    },
                    timeout=10.0
                )
                
                return response.json()
                
        except Exception as e:
            logger.error(f"Pre-checkout error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def get_payment_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get payment statistics for admin"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Total payments
        total_pipeline = [
            {"$match": {"status": "completed", "createdAt": {"$gte": cutoff}}},
            {"$group": {
                "_id": None,
                "totalStars": {"$sum": "$amount"},
                "totalUsd": {"$sum": "$amountUsd"},
                "count": {"$sum": 1}
            }}
        ]
        total = await self.db.payments.aggregate(total_pipeline).to_list(1)
        
        # Active subscriptions
        now = datetime.now(timezone.utc)
        active_subs = await self.db.subscriptions.count_documents({
            "status": "active",
            "expiresAt": {"$gt": now}
        })
        
        # MRR calculation
        mrr = active_subs * SUBSCRIPTION_PRICE_USD  # $2 per subscription
        
        # Daily breakdown
        daily_pipeline = [
            {"$match": {"status": "completed", "createdAt": {"$gte": cutoff}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                "revenue": {"$sum": "$amountUsd"},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": -1}},
            {"$limit": 30}
        ]
        daily = await self.db.payments.aggregate(daily_pipeline).to_list(30)
        
        return {
            "ok": True,
            "totalRevenue": total[0]["totalUsd"] if total else 0,
            "totalPayments": total[0]["count"] if total else 0,
            "activeSubscriptions": active_subs,
            "mrr": mrr,
            "arr": mrr * 12,
            "dailyBreakdown": daily,
            "days": days
        }


async def ensure_payment_indexes(db):
    """Create indexes for payment collections"""
    # payments
    await db.payments.create_index("paymentId", unique=True)
    await db.payments.create_index("userId")
    await db.payments.create_index([("createdAt", -1)])
    
    # subscriptions
    await db.subscriptions.create_index("userId", unique=True)
    await db.subscriptions.create_index("status")
    await db.subscriptions.create_index("expiresAt")
    
    # invoices
    await db.invoices.create_index("invoiceId", unique=True)
    await db.invoices.create_index("userId")
    
    logger.info("Payment indexes created")
