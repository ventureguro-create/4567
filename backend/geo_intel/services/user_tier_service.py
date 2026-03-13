"""
User Tier Service - Freemium Model
FREE / TRIAL (7 days) / PRO ($1/month)

FREE limitations:
- Radius: 2km max
- Signal delay: 10 min
- No photos
- No analytics

TRIAL (7 days):
- Full access
- All features

PRO ($1/month):
- No limitations
- Priority alerts
- Extended radius (5km)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Tier definitions
TIER_FREE = "FREE"
TIER_TRIAL = "TRIAL"
TIER_PRO = "PRO"

# Tier limits
TIER_LIMITS = {
    TIER_FREE: {
        "maxRadius": 2000,  # 2km
        "signalDelay": 600,  # 10 minutes delay
        "canSendPhoto": False,
        "canViewAnalytics": False,
        "canReceiveInstantAlerts": False,
        "dailyReportLimit": 5,
        "label": "Basic",
        "labelUa": "Базовий"
    },
    TIER_TRIAL: {
        "maxRadius": 5000,  # 5km
        "signalDelay": 0,  # instant
        "canSendPhoto": True,
        "canViewAnalytics": True,
        "canReceiveInstantAlerts": True,
        "dailyReportLimit": 50,
        "label": "Trial",
        "labelUa": "Пробний"
    },
    TIER_PRO: {
        "maxRadius": 10000,  # 10km
        "signalDelay": 0,  # instant
        "canSendPhoto": True,
        "canViewAnalytics": True,
        "canReceiveInstantAlerts": True,
        "dailyReportLimit": -1,  # unlimited
        "label": "Premium",
        "labelUa": "Преміум"
    }
}

TRIAL_DURATION_DAYS = 7


class UserTierService:
    """Manages user tiers and access control"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_user_tiers
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.collection.create_index("actorId", unique=True)
        await self.collection.create_index("tier")
        await self.collection.create_index("trialExpiresAt")
        await self.collection.create_index("proExpiresAt")
    
    async def get_user_tier(self, actor_id: str) -> Dict[str, Any]:
        """
        Get user's current tier with all limits.
        Auto-creates FREE tier for new users.
        Auto-starts TRIAL for first-time users.
        """
        doc = await self.collection.find_one({"actorId": actor_id})
        now = datetime.now(timezone.utc)
        
        if not doc:
            # New user - start with TRIAL
            doc = await self._create_user_tier(actor_id, start_trial=True)
        
        # Check tier status
        tier = doc.get("tier", TIER_FREE)
        
        # Check if PRO expired
        if tier == TIER_PRO:
            pro_expires = doc.get("proExpiresAt")
            if pro_expires and now > pro_expires:
                # PRO expired, downgrade to FREE
                tier = TIER_FREE
                await self.collection.update_one(
                    {"actorId": actor_id},
                    {"$set": {"tier": TIER_FREE, "updatedAt": now}}
                )
        
        # Check if TRIAL expired
        elif tier == TIER_TRIAL:
            trial_expires = doc.get("trialExpiresAt")
            if trial_expires and now > trial_expires:
                # TRIAL expired, downgrade to FREE
                tier = TIER_FREE
                await self.collection.update_one(
                    {"actorId": actor_id},
                    {"$set": {"tier": TIER_FREE, "updatedAt": now}}
                )
        
        # Get limits
        limits = TIER_LIMITS.get(tier, TIER_LIMITS[TIER_FREE])
        
        # Calculate remaining time
        remaining_days = None
        if tier == TIER_TRIAL:
            trial_expires = doc.get("trialExpiresAt")
            if trial_expires:
                remaining = (trial_expires - now).days
                remaining_days = max(0, remaining)
        elif tier == TIER_PRO:
            pro_expires = doc.get("proExpiresAt")
            if pro_expires:
                remaining = (pro_expires - now).days
                remaining_days = max(0, remaining)
        
        return {
            "actorId": actor_id,
            "tier": tier,
            "limits": limits,
            "trialUsed": doc.get("trialUsed", False),
            "trialExpiresAt": doc.get("trialExpiresAt"),
            "proExpiresAt": doc.get("proExpiresAt"),
            "remainingDays": remaining_days,
            "createdAt": doc.get("createdAt"),
        }
    
    async def _create_user_tier(self, actor_id: str, start_trial: bool = True) -> Dict[str, Any]:
        """Create tier record for new user"""
        now = datetime.now(timezone.utc)
        
        if start_trial:
            tier = TIER_TRIAL
            trial_expires = now + timedelta(days=TRIAL_DURATION_DAYS)
            trial_used = True
        else:
            tier = TIER_FREE
            trial_expires = None
            trial_used = False
        
        doc = {
            "actorId": actor_id,
            "tier": tier,
            "trialUsed": trial_used,
            "trialExpiresAt": trial_expires,
            "proExpiresAt": None,
            "createdAt": now,
            "updatedAt": now,
        }
        
        await self.collection.insert_one(doc)
        logger.info(f"Created tier for {actor_id}: {tier}")
        return doc
    
    async def activate_pro(self, actor_id: str, months: int = 1) -> Dict[str, Any]:
        """Activate PRO subscription for N months"""
        now = datetime.now(timezone.utc)
        
        # Get current tier to check if extending
        current = await self.collection.find_one({"actorId": actor_id})
        
        if current and current.get("tier") == TIER_PRO and current.get("proExpiresAt"):
            # Extend existing subscription
            base_date = current["proExpiresAt"]
            if base_date < now:
                base_date = now
        else:
            base_date = now
        
        pro_expires = base_date + timedelta(days=30 * months)
        
        await self.collection.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "tier": TIER_PRO,
                    "proExpiresAt": pro_expires,
                    "updatedAt": now
                },
                "$setOnInsert": {
                    "createdAt": now,
                    "trialUsed": True
                }
            },
            upsert=True
        )
        
        logger.info(f"Activated PRO for {actor_id} until {pro_expires}")
        return await self.get_user_tier(actor_id)
    
    async def check_can_use_feature(self, actor_id: str, feature: str) -> Dict[str, Any]:
        """
        Check if user can use a specific feature.
        Returns {"allowed": bool, "reason": str, "upgrade_prompt": str}
        """
        tier_data = await self.get_user_tier(actor_id)
        tier = tier_data["tier"]
        limits = tier_data["limits"]
        
        # Feature checks
        if feature == "send_photo":
            if not limits["canSendPhoto"]:
                return {
                    "allowed": False,
                    "reason": "Фото доступне тільки в PRO",
                    "upgradePrompt": "⭐ Оформіть підписку для надсилання фото"
                }
        
        elif feature == "instant_alert":
            if not limits["canReceiveInstantAlerts"]:
                return {
                    "allowed": False,
                    "reason": "Миттєві сповіщення доступні в PRO",
                    "upgradePrompt": "⭐ Оформіть підписку для миттєвих сповіщень"
                }
        
        elif feature == "analytics":
            if not limits["canViewAnalytics"]:
                return {
                    "allowed": False,
                    "reason": "Аналітика доступна в PRO",
                    "upgradePrompt": "⭐ Оформіть підписку для доступу до аналітики"
                }
        
        elif feature.startswith("radius_"):
            requested_radius = int(feature.replace("radius_", ""))
            if requested_radius > limits["maxRadius"]:
                return {
                    "allowed": False,
                    "reason": f"Радіус {requested_radius}м доступний тільки в PRO",
                    "upgradePrompt": f"⭐ Ваш максимальний радіус: {limits['maxRadius']}м"
                }
        
        return {"allowed": True, "reason": None, "upgradePrompt": None}
    
    async def get_signal_delay(self, actor_id: str) -> int:
        """Get signal delay in seconds for user"""
        tier_data = await self.get_user_tier(actor_id)
        return tier_data["limits"]["signalDelay"]
    
    async def can_report_today(self, actor_id: str) -> Dict[str, Any]:
        """Check if user can report more signals today"""
        tier_data = await self.get_user_tier(actor_id)
        limit = tier_data["limits"]["dailyReportLimit"]
        
        if limit == -1:
            return {"allowed": True, "remaining": -1}
        
        # Count today's reports
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        count = await self.db.tg_crowd_signals.count_documents({
            "actorId": actor_id,
            "createdAt": {"$gte": today_start}
        })
        
        if count >= limit:
            return {
                "allowed": False,
                "remaining": 0,
                "reason": f"Ліміт {limit} сигналів на день вичерпано",
                "upgradePrompt": "⭐ Оформіть PRO для необмежених сигналів"
            }
        
        return {"allowed": True, "remaining": limit - count}
    
    async def format_tier_info(self, actor_id: str) -> str:
        """Format tier info for display"""
        tier_data = await self.get_user_tier(actor_id)
        tier = tier_data["tier"]
        limits = tier_data["limits"]
        remaining = tier_data.get("remainingDays")
        
        label = limits["labelUa"]
        
        if tier == TIER_FREE:
            return f"📊 План: {label}\n\n⭐ Оформіть підписку для повного доступу"
        elif tier == TIER_TRIAL:
            return f"🎁 План: {label}\n⏱ Залишилось: {remaining} днів"
        elif tier == TIER_PRO:
            return f"⭐ План: {label}\n⏱ Активний до: {remaining} днів"
        
        return f"План: {label}"
