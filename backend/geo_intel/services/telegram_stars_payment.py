"""
Telegram Stars Payment Service - Subscription handling via Telegram Stars

Telegram Stars:
- Built-in Telegram payment system
- No external payment processor needed
- Instant payment confirmation

Flow:
1. User clicks "Subscribe" button
2. Bot sends invoice with Stars price
3. User pays with Stars
4. pre_checkout_query validates
5. successful_payment activates subscription
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Pricing in Telegram Stars
# 1 Star ≈ $0.02, so $1 ≈ 50 Stars
PRICE_PRO_MONTHLY_STARS = 50  # $1/month
PRICE_PRO_YEARLY_STARS = 500  # $10/year (save 16%)

# Subscription durations
DURATION_MONTHLY = "monthly"
DURATION_YEARLY = "yearly"


class TelegramStarsPaymentService:
    """Handles Telegram Stars payments for PRO subscriptions"""
    
    def __init__(self, db):
        self.db = db
        self.subscriptions = db.geo_subscriptions
        self.payments = db.geo_payments
        self.bot_token = os.environ.get("TG_BOT_TOKEN")
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.subscriptions.create_index("actorId", unique=True)
        await self.subscriptions.create_index("status")
        await self.subscriptions.create_index("expiresAt")
        await self.payments.create_index("actorId")
        await self.payments.create_index("telegramPaymentId")
        await self.payments.create_index("createdAt")
    
    def create_invoice_payload(self, actor_id: str, duration: str = DURATION_MONTHLY) -> str:
        """Create invoice payload for tracking"""
        return f"pro_{duration}_{actor_id}"
    
    def parse_invoice_payload(self, payload: str) -> Dict[str, Any]:
        """Parse invoice payload"""
        parts = payload.split("_")
        if len(parts) >= 3:
            return {
                "plan": parts[0],
                "duration": parts[1],
                "actorId": "_".join(parts[2:])
            }
        return {"error": "Invalid payload"}
    
    def get_invoice_data(self, duration: str = DURATION_MONTHLY) -> Dict[str, Any]:
        """Get invoice data for Telegram sendInvoice"""
        if duration == DURATION_YEARLY:
            return {
                "title": "Radar PRO (рік)",
                "description": "Повний доступ на 1 рік. Без реклами, розширений радіус, миттєві сповіщення.",
                "prices": [{"label": "PRO 1 рік", "amount": PRICE_PRO_YEARLY_STARS}],
                "currency": "XTR",  # Telegram Stars currency code
            }
        
        return {
            "title": "Radar PRO (місяць)",
            "description": "Повний доступ на 1 місяць. Без реклами, розширений радіус, миттєві сповіщення.",
            "prices": [{"label": "PRO 1 місяць", "amount": PRICE_PRO_MONTHLY_STARS}],
            "currency": "XTR",
        }
    
    async def handle_pre_checkout(
        self,
        pre_checkout_query_id: str,
        actor_id: str,
        payload: str
    ) -> Dict[str, Any]:
        """
        Handle pre_checkout_query - validate payment before processing.
        Must respond within 10 seconds.
        """
        import httpx
        
        # Parse payload
        parsed = self.parse_invoice_payload(payload)
        if "error" in parsed:
            # Reject
            await self._answer_pre_checkout(pre_checkout_query_id, ok=False, error_message="Invalid invoice")
            return {"ok": False, "error": "Invalid payload"}
        
        # Check if user is banned
        from .admin_moderation_service import AdminModerationService
        mod_svc = AdminModerationService(self.db)
        ban_check = await mod_svc.is_user_banned(actor_id)
        if ban_check.get("banned"):
            await self._answer_pre_checkout(
                pre_checkout_query_id,
                ok=False,
                error_message="Ваш акаунт заблоковано"
            )
            return {"ok": False, "error": "User banned"}
        
        # All good - approve
        await self._answer_pre_checkout(pre_checkout_query_id, ok=True)
        
        return {"ok": True}
    
    async def _answer_pre_checkout(
        self,
        query_id: str,
        ok: bool,
        error_message: str = None
    ):
        """Send answer to pre_checkout_query"""
        import httpx
        
        if not self.bot_token:
            logger.error("BOT_TOKEN not set, cannot answer pre_checkout")
            return
        
        payload = {"pre_checkout_query_id": query_id, "ok": ok}
        if not ok and error_message:
            payload["error_message"] = error_message
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/answerPreCheckoutQuery",
                    json=payload,
                    timeout=10.0
                )
        except Exception as e:
            logger.error(f"Failed to answer pre_checkout: {e}")
    
    async def handle_successful_payment(
        self,
        actor_id: str,
        chat_id: int,
        payment_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle successful_payment - activate subscription.
        Called after Telegram confirms payment.
        """
        now = datetime.now(timezone.utc)
        
        # Extract payment info
        payload = payment_data.get("invoice_payload", "")
        total_amount = payment_data.get("total_amount", 0)
        currency = payment_data.get("currency", "XTR")
        telegram_payment_id = payment_data.get("telegram_payment_charge_id", "")
        
        # Parse payload
        parsed = self.parse_invoice_payload(payload)
        duration = parsed.get("duration", DURATION_MONTHLY)
        
        # Calculate expiration
        if duration == DURATION_YEARLY:
            expires_at = now + timedelta(days=365)
        else:
            expires_at = now + timedelta(days=30)
        
        # Record payment
        await self.payments.insert_one({
            "actorId": actor_id,
            "chatId": chat_id,
            "telegramPaymentId": telegram_payment_id,
            "amount": total_amount,
            "currency": currency,
            "duration": duration,
            "payload": payload,
            "createdAt": now
        })
        
        # Activate/extend subscription
        existing = await self.subscriptions.find_one({"actorId": actor_id})
        
        if existing and existing.get("expiresAt") and existing["expiresAt"] > now:
            # Extend existing subscription
            new_expires = existing["expiresAt"] + (
                timedelta(days=365) if duration == DURATION_YEARLY else timedelta(days=30)
            )
        else:
            new_expires = expires_at
        
        await self.subscriptions.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "actorId": actor_id,
                    "status": "active",
                    "plan": "pro",
                    "duration": duration,
                    "expiresAt": new_expires,
                    "lastPaymentAt": now,
                    "updatedAt": now
                },
                "$setOnInsert": {
                    "createdAt": now
                }
            },
            upsert=True
        )
        
        # Update user tier
        from .user_tier_service import UserTierService
        tier_svc = UserTierService(self.db)
        months = 12 if duration == DURATION_YEARLY else 1
        await tier_svc.activate_pro(actor_id, months=months)
        
        logger.info(f"Subscription activated: {actor_id}, duration={duration}, expires={new_expires}")
        
        return {
            "ok": True,
            "actorId": actor_id,
            "plan": "pro",
            "expiresAt": new_expires.isoformat(),
            "duration": duration
        }
    
    async def get_subscription(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """Get user's subscription status"""
        sub = await self.subscriptions.find_one(
            {"actorId": actor_id},
            {"_id": 0}
        )
        
        if not sub:
            return None
        
        now = datetime.now(timezone.utc)
        expires_at = sub.get("expiresAt")
        
        if expires_at and now > expires_at:
            # Expired
            sub["status"] = "expired"
            await self.subscriptions.update_one(
                {"actorId": actor_id},
                {"$set": {"status": "expired"}}
            )
        
        return sub
    
    async def cancel_subscription(self, actor_id: str) -> Dict[str, Any]:
        """Cancel subscription (will expire at end of period)"""
        result = await self.subscriptions.update_one(
            {"actorId": actor_id},
            {"$set": {"status": "cancelled", "cancelledAt": datetime.now(timezone.utc)}}
        )
        
        if result.modified_count > 0:
            return {"ok": True, "action": "cancelled"}
        return {"ok": False, "error": "No subscription found"}
    
    def get_subscribe_keyboard(self) -> Dict[str, Any]:
        """Get keyboard for subscription options"""
        return {
            "inline_keyboard": [
                [{"text": f"⭐ {PRICE_PRO_MONTHLY_STARS} Stars / місяць", "callback_data": "subscribe_monthly"}],
                [{"text": f"⭐ {PRICE_PRO_YEARLY_STARS} Stars / рік (−16%)", "callback_data": "subscribe_yearly"}],
                [{"text": "↩️ Назад", "callback_data": "back_profile"}]
            ]
        }
    
    async def send_invoice(
        self,
        chat_id: int,
        actor_id: str,
        duration: str = DURATION_MONTHLY
    ) -> Dict[str, Any]:
        """Send payment invoice to user"""
        import httpx
        
        if not self.bot_token:
            return {"ok": False, "error": "BOT_TOKEN not configured"}
        
        invoice_data = self.get_invoice_data(duration)
        payload = self.create_invoice_payload(actor_id, duration)
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.bot_token}/sendInvoice",
                    json={
                        "chat_id": chat_id,
                        "title": invoice_data["title"],
                        "description": invoice_data["description"],
                        "payload": payload,
                        "currency": invoice_data["currency"],
                        "prices": invoice_data["prices"],
                        "start_parameter": "subscribe",
                        "is_flexible": False,
                    },
                    timeout=10.0
                )
                
                result = response.json()
                if not result.get("ok"):
                    logger.error(f"Failed to send invoice: {result}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to send invoice: {e}")
            return {"ok": False, "error": str(e)}


class PaymentService(TelegramStarsPaymentService):
    """Alias for compatibility with existing code"""
    pass


class SubscriptionService(TelegramStarsPaymentService):
    """Alias for subscription-focused operations"""
    pass
