"""
Trust Score Service - User reputation system

Trust Score determines:
- Auto-publish vs moderation
- Signal weight/confidence boost
- Report priority

Levels:
0-3 reports: MODERATED (all require admin approval)
4-10 reports: PARTIAL (photos require approval)
11+ reports: TRUSTED (auto-publish)

Score factors:
- Confirmed reports: +10 points
- Rejected reports: -5 points
- User confirmations received: +2 points
- Days active: +1 per day
- Streak bonus: +5 for 3 consecutive days
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Trust levels
TRUST_LEVEL_NEW = "NEW"           # 0-3 confirmed reports
TRUST_LEVEL_REGULAR = "REGULAR"   # 4-10 confirmed reports
TRUST_LEVEL_TRUSTED = "TRUSTED"   # 11+ confirmed reports
TRUST_LEVEL_VIP = "VIP"           # 30+ reports, top performers

# Points per action
POINTS_CONFIRMED_REPORT = 10
POINTS_REJECTED_REPORT = -5
POINTS_CONFIRMATION_RECEIVED = 2
POINTS_DAILY_ACTIVITY = 1
POINTS_STREAK_BONUS = 5

# Thresholds
THRESHOLD_REGULAR = 4
THRESHOLD_TRUSTED = 11
THRESHOLD_VIP = 30


class TrustScoreService:
    """Manages user trust scores and moderation requirements"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_trust_scores
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.collection.create_index("actorId", unique=True)
        await self.collection.create_index("level")
        await self.collection.create_index("score")
        await self.collection.create_index([("score", -1)])  # For leaderboard
    
    async def get_trust_score(self, actor_id: str) -> Dict[str, Any]:
        """Get user's trust score, create if not exists"""
        doc = await self.collection.find_one({"actorId": actor_id})
        
        if not doc:
            doc = await self._create_trust_score(actor_id)
        
        return self._format_trust_data(doc)
    
    async def _create_trust_score(self, actor_id: str) -> Dict[str, Any]:
        """Create new trust score record"""
        now = datetime.now(timezone.utc)
        doc = {
            "actorId": actor_id,
            "score": 0,
            "level": TRUST_LEVEL_NEW,
            "confirmedReports": 0,
            "rejectedReports": 0,
            "totalReports": 0,
            "confirmationsReceived": 0,
            "daysActive": 0,
            "currentStreak": 0,
            "longestStreak": 0,
            "lastActivityAt": now,
            "lastStreakDate": None,
            "createdAt": now,
            "updatedAt": now,
        }
        await self.collection.insert_one(doc)
        return doc
    
    def _format_trust_data(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format trust data for API response"""
        if not doc:
            return {"level": TRUST_LEVEL_NEW, "score": 0}
        
        return {
            "actorId": doc.get("actorId"),
            "score": doc.get("score", 0),
            "level": doc.get("level", TRUST_LEVEL_NEW),
            "confirmedReports": doc.get("confirmedReports", 0),
            "rejectedReports": doc.get("rejectedReports", 0),
            "totalReports": doc.get("totalReports", 0),
            "confirmationsReceived": doc.get("confirmationsReceived", 0),
            "currentStreak": doc.get("currentStreak", 0),
            "longestStreak": doc.get("longestStreak", 0),
        }
    
    def _calculate_level(self, confirmed_reports: int, score: int) -> str:
        """Calculate trust level based on confirmed reports"""
        if confirmed_reports >= THRESHOLD_VIP:
            return TRUST_LEVEL_VIP
        elif confirmed_reports >= THRESHOLD_TRUSTED:
            return TRUST_LEVEL_TRUSTED
        elif confirmed_reports >= THRESHOLD_REGULAR:
            return TRUST_LEVEL_REGULAR
        return TRUST_LEVEL_NEW
    
    async def add_report(self, actor_id: str, was_confirmed: bool) -> Dict[str, Any]:
        """
        Record a new report and update trust score.
        Called after admin moderation or crowd confirmation.
        """
        now = datetime.now(timezone.utc)
        doc = await self.collection.find_one({"actorId": actor_id})
        
        if not doc:
            doc = await self._create_trust_score(actor_id)
        
        # Calculate score change
        if was_confirmed:
            score_delta = POINTS_CONFIRMED_REPORT
            update_inc = {
                "score": score_delta,
                "confirmedReports": 1,
                "totalReports": 1
            }
        else:
            score_delta = POINTS_REJECTED_REPORT
            update_inc = {
                "score": score_delta,
                "rejectedReports": 1,
                "totalReports": 1
            }
        
        # Check streak
        last_activity = doc.get("lastActivityAt")
        last_streak_date = doc.get("lastStreakDate")
        current_streak = doc.get("currentStreak", 0)
        
        today = now.date()
        
        if last_streak_date:
            last_date = last_streak_date.date() if hasattr(last_streak_date, 'date') else last_streak_date
            if last_date == today - timedelta(days=1):
                # Continue streak
                current_streak += 1
                if current_streak == 3:
                    update_inc["score"] = update_inc.get("score", 0) + POINTS_STREAK_BONUS
            elif last_date != today:
                # Reset streak
                current_streak = 1
        else:
            current_streak = 1
        
        # Update streak fields
        longest_streak = max(doc.get("longestStreak", 0), current_streak)
        
        # Calculate new level
        new_confirmed = doc.get("confirmedReports", 0) + (1 if was_confirmed else 0)
        new_score = doc.get("score", 0) + update_inc["score"]
        new_level = self._calculate_level(new_confirmed, new_score)
        
        # Perform update
        await self.collection.update_one(
            {"actorId": actor_id},
            {
                "$inc": update_inc,
                "$set": {
                    "level": new_level,
                    "currentStreak": current_streak,
                    "longestStreak": longest_streak,
                    "lastActivityAt": now,
                    "lastStreakDate": now,
                    "updatedAt": now
                }
            }
        )
        
        logger.info(f"Trust updated for {actor_id}: confirmed={was_confirmed}, score_delta={update_inc['score']}, level={new_level}")
        
        return await self.get_trust_score(actor_id)
    
    async def add_confirmation_received(self, actor_id: str) -> Dict[str, Any]:
        """Add points when user's report gets confirmed by others"""
        now = datetime.now(timezone.utc)
        
        await self.collection.update_one(
            {"actorId": actor_id},
            {
                "$inc": {
                    "score": POINTS_CONFIRMATION_RECEIVED,
                    "confirmationsReceived": 1
                },
                "$set": {"updatedAt": now}
            },
            upsert=True
        )
        
        return await self.get_trust_score(actor_id)
    
    async def requires_moderation(self, actor_id: str, has_photo: bool = False) -> Dict[str, Any]:
        """
        Check if user's report requires admin moderation.
        
        Returns:
        {
            "required": bool,
            "reason": str,
            "autoPublish": bool
        }
        """
        trust = await self.get_trust_score(actor_id)
        level = trust.get("level", TRUST_LEVEL_NEW)
        
        if level == TRUST_LEVEL_VIP:
            return {
                "required": False,
                "reason": "VIP user",
                "autoPublish": True
            }
        
        if level == TRUST_LEVEL_TRUSTED:
            return {
                "required": False,
                "reason": "Trusted user",
                "autoPublish": True
            }
        
        if level == TRUST_LEVEL_REGULAR:
            if has_photo:
                return {
                    "required": True,
                    "reason": "Photo requires moderation",
                    "autoPublish": False
                }
            return {
                "required": False,
                "reason": "Regular user, no photo",
                "autoPublish": True
            }
        
        # NEW level - always requires moderation
        return {
            "required": True,
            "reason": "New user requires moderation",
            "autoPublish": False
        }
    
    async def get_signal_confidence_boost(self, actor_id: str) -> float:
        """
        Get confidence boost for user's signals.
        VIP: +0.3, TRUSTED: +0.2, REGULAR: +0.1, NEW: 0
        """
        trust = await self.get_trust_score(actor_id)
        level = trust.get("level", TRUST_LEVEL_NEW)
        
        boosts = {
            TRUST_LEVEL_VIP: 0.3,
            TRUST_LEVEL_TRUSTED: 0.2,
            TRUST_LEVEL_REGULAR: 0.1,
            TRUST_LEVEL_NEW: 0.0
        }
        
        return boosts.get(level, 0.0)
    
    async def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by trust score"""
        cursor = self.collection.find(
            {"confirmedReports": {"$gt": 0}},
            {"_id": 0}
        ).sort("score", -1).limit(limit)
        
        results = []
        rank = 1
        async for doc in cursor:
            results.append({
                "rank": rank,
                "actorId": doc.get("actorId"),
                "score": doc.get("score", 0),
                "level": doc.get("level"),
                "confirmedReports": doc.get("confirmedReports", 0),
                "currentStreak": doc.get("currentStreak", 0),
            })
            rank += 1
        
        return results
    
    async def format_trust_badge(self, actor_id: str) -> str:
        """Get emoji badge for trust level"""
        trust = await self.get_trust_score(actor_id)
        level = trust.get("level", TRUST_LEVEL_NEW)
        
        badges = {
            TRUST_LEVEL_VIP: "🏆",
            TRUST_LEVEL_TRUSTED: "⭐",
            TRUST_LEVEL_REGULAR: "✓",
            TRUST_LEVEL_NEW: ""
        }
        
        return badges.get(level, "")
