"""
Referral System - Main Service
Handles referral links, tracking, and rewards
30% per paying referral = $0.60 (recurring monthly)
"""
import os
import logging
import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Constants
REFERRAL_REWARD_PERCENT = 0.30  # 30% від підписки
SUBSCRIPTION_PRICE_USD = 2.00   # $2/month
REFERRAL_REWARD_USD = SUBSCRIPTION_PRICE_USD * REFERRAL_REWARD_PERCENT  # $0.60
SUBSCRIPTION_PRICE_STARS = 200  # ~200 Telegram Stars
MAX_REFERRALS_PER_DAY = 100  # Anti-abuse limit


def generate_referral_code(length: int = 8) -> str:
    """Generate unique referral code like ref_7K92J"""
    chars = string.ascii_uppercase + string.digits
    code = ''.join(secrets.choice(chars) for _ in range(length))
    return f"ref_{code}"


class ReferralService:
    """Referral system service"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_or_create_referral_code(self, user_id: str) -> str:
        """Get existing or create new referral code for user"""
        # Check if user already has a code
        user = await self.db.referral_users.find_one({"userId": user_id})
        
        if user and user.get("referralCode"):
            return user["referralCode"]
        
        # Generate new unique code
        for _ in range(10):  # Max 10 attempts
            code = generate_referral_code()
            existing = await self.db.referral_users.find_one({"referralCode": code})
            if not existing:
                break
        
        # Create or update user record
        await self.db.referral_users.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "referralCode": code,
                    "updatedAt": datetime.now(timezone.utc)
                },
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc),
                    "referredBy": None,
                    "referralCount": 0,
                    "activeReferrals": 0,
                    "totalEarned": 0.0
                }
            },
            upsert=True
        )
        
        return code
    
    async def register_referral(
        self,
        new_user_id: str,
        referral_code: str,
        username: str = None
    ) -> Dict[str, Any]:
        """
        Register new user from referral link.
        Called when user starts bot with ?start=ref_XXXX
        """
        # Validate referral code
        referrer = await self.db.referral_users.find_one({"referralCode": referral_code})
        if not referrer:
            return {"ok": False, "error": "invalid_code"}
        
        referrer_id = referrer["userId"]
        
        # Anti-abuse: can't refer yourself
        if referrer_id == new_user_id:
            return {"ok": False, "error": "self_referral"}
        
        # Check if user already has a referrer
        existing = await self.db.referral_users.find_one({"userId": new_user_id})
        if existing and existing.get("referredBy"):
            return {"ok": False, "error": "already_referred"}
        
        # Check daily limit for referrer
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await self.db.referrals.count_documents({
            "referrerId": referrer_id,
            "createdAt": {"$gte": today_start}
        })
        
        if today_count >= MAX_REFERRALS_PER_DAY:
            logger.warning(f"Referrer {referrer_id} hit daily limit")
            return {"ok": False, "error": "daily_limit"}
        
        # Create referral record
        referral = {
            "referrerId": referrer_id,
            "referredUserId": new_user_id,
            "referredUsername": username,
            "referralCode": referral_code,
            "status": "registered",  # registered -> paid -> active
            "rewardPaid": 0.0,
            "paymentCount": 0,
            "createdAt": datetime.now(timezone.utc),
            "lastPaymentAt": None
        }
        
        await self.db.referrals.insert_one(referral)
        
        # Update new user record
        await self.db.referral_users.update_one(
            {"userId": new_user_id},
            {
                "$set": {
                    "referredBy": referrer_id,
                    "referredByCode": referral_code,
                    "updatedAt": datetime.now(timezone.utc)
                },
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc),
                    "referralCode": None,
                    "referralCount": 0,
                    "activeReferrals": 0,
                    "totalEarned": 0.0
                }
            },
            upsert=True
        )
        
        # Increment referrer's count
        await self.db.referral_users.update_one(
            {"userId": referrer_id},
            {"$inc": {"referralCount": 1}}
        )
        
        logger.info(f"Referral registered: {new_user_id} by {referrer_id}")
        
        return {
            "ok": True,
            "referrerId": referrer_id,
            "referralCode": referral_code
        }
    
    async def process_payment_reward(
        self,
        paying_user_id: str,
        payment_amount_usd: float = SUBSCRIPTION_PRICE_USD
    ) -> Dict[str, Any]:
        """
        Process referral reward when user pays subscription.
        Called after successful_payment webhook.
        Returns $0.30 to referrer for each payment.
        """
        # Get user's referrer
        user = await self.db.referral_users.find_one({"userId": paying_user_id})
        if not user or not user.get("referredBy"):
            return {"ok": True, "reward": 0, "reason": "no_referrer"}
        
        referrer_id = user["referredBy"]
        
        # Calculate reward (30% of subscription)
        reward = REFERRAL_REWARD_USD
        
        # Update referral record
        result = await self.db.referrals.update_one(
            {"referrerId": referrer_id, "referredUserId": paying_user_id},
            {
                "$set": {
                    "status": "active",
                    "lastPaymentAt": datetime.now(timezone.utc)
                },
                "$inc": {
                    "rewardPaid": reward,
                    "paymentCount": 1
                }
            }
        )
        
        if result.modified_count == 0:
            return {"ok": False, "error": "referral_not_found"}
        
        # Add reward to referrer's wallet
        from .wallet_service import WalletService
        wallet_svc = WalletService(self.db)
        await wallet_svc.add_referral_reward(
            user_id=referrer_id,
            amount=reward,
            from_user_id=paying_user_id,
            description=f"Referral reward from payment"
        )
        
        # Update referrer stats
        await self.db.referral_users.update_one(
            {"userId": referrer_id},
            {
                "$inc": {"totalEarned": reward},
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )
        
        # Update active referrals count
        active_count = await self.db.referrals.count_documents({
            "referrerId": referrer_id,
            "status": "active",
            "lastPaymentAt": {"$gte": datetime.now(timezone.utc) - timedelta(days=35)}
        })
        
        await self.db.referral_users.update_one(
            {"userId": referrer_id},
            {"$set": {"activeReferrals": active_count}}
        )
        
        logger.info(f"Referral reward: {referrer_id} earned ${reward} from {paying_user_id}")
        
        return {
            "ok": True,
            "referrerId": referrer_id,
            "reward": reward,
            "totalEarned": (user.get("totalEarned", 0) + reward)
        }
    
    async def get_user_referral_stats(self, user_id: str) -> Dict[str, Any]:
        """Get referral statistics for user"""
        # Get user record
        user = await self.db.referral_users.find_one({"userId": user_id})
        
        if not user:
            # Create new user record
            code = await self.get_or_create_referral_code(user_id)
            user = await self.db.referral_users.find_one({"userId": user_id})
        
        # Get wallet balance
        from .wallet_service import WalletService
        wallet_svc = WalletService(self.db)
        wallet = await wallet_svc.get_balance(user_id)
        
        # Count active referrals (paid in last 35 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=35)
        active_count = await self.db.referrals.count_documents({
            "referrerId": user_id,
            "status": "active",
            "lastPaymentAt": {"$gte": cutoff}
        })
        
        # Total referrals
        total_count = await self.db.referrals.count_documents({"referrerId": user_id})
        
        # Monthly income (active referrals × $0.30)
        monthly_income = active_count * REFERRAL_REWARD_USD
        
        return {
            "ok": True,
            "referralCode": user.get("referralCode"),
            "referralLink": f"t.me/ARKHOR_bot?start={user.get('referralCode', '')}",
            "totalReferrals": total_count,
            "activeReferrals": active_count,
            "totalEarned": user.get("totalEarned", 0),
            "monthlyIncome": monthly_income,
            "balance": wallet.get("referralBalance", 0),
            "withdrawn": wallet.get("totalWithdrawn", 0)
        }
    
    async def get_referral_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top referrers leaderboard"""
        pipeline = [
            {"$match": {"referralCount": {"$gt": 0}}},
            {"$sort": {"totalEarned": -1}},
            {"$limit": limit},
            {"$project": {
                "_id": 0,
                "userId": 1,
                "referralCount": 1,
                "activeReferrals": 1,
                "totalEarned": 1
            }}
        ]
        
        leaders = await self.db.referral_users.aggregate(pipeline).to_list(limit)
        
        # Add rank
        for i, leader in enumerate(leaders, 1):
            leader["rank"] = i
        
        return leaders
    
    async def get_user_referrals(
        self,
        user_id: str,
        limit: int = 50,
        skip: int = 0
    ) -> Dict[str, Any]:
        """Get list of user's referrals"""
        referrals = await self.db.referrals.find(
            {"referrerId": user_id},
            {"_id": 0}
        ).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        
        total = await self.db.referrals.count_documents({"referrerId": user_id})
        
        return {
            "ok": True,
            "items": referrals,
            "total": total
        }


async def ensure_referral_indexes(db):
    """Create indexes for referral collections"""
    # referral_users
    await db.referral_users.create_index("userId", unique=True)
    await db.referral_users.create_index("referralCode", unique=True, sparse=True)
    await db.referral_users.create_index("referredBy")
    await db.referral_users.create_index([("totalEarned", -1)])
    
    # referrals
    await db.referrals.create_index([("referrerId", 1), ("referredUserId", 1)], unique=True)
    await db.referrals.create_index("referrerId")
    await db.referrals.create_index("referredUserId")
    await db.referrals.create_index("status")
    await db.referrals.create_index("createdAt")
    
    logger.info("Referral indexes created")
