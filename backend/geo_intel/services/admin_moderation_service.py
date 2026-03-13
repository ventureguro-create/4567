"""
Admin Moderation Service - Signal moderation for bot admins

Features:
- Inline admin panel for moderators
- Approve/reject signals with photos
- Ban repeat offenders
- Moderation queue management
- Admin notification system

Admin Detection:
- Checks ADMIN_IDS environment variable
- Format: comma-separated Telegram IDs
"""
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Load admin IDs from env
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "5329782249")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",") if x.strip().isdigit()]

# Moderation status
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"

# Ban durations
BAN_DURATION_HOURS = {
    "warning": 0,
    "short": 24,
    "medium": 168,  # 7 days
    "long": 720,    # 30 days
    "permanent": 8760  # 1 year
}


class AdminModerationService:
    """Handles signal moderation for admins"""
    
    def __init__(self, db):
        self.db = db
        self.queue_collection = db.geo_moderation_queue
        self.bans_collection = db.geo_user_bans
        self.admin_ids = ADMIN_IDS
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.queue_collection.create_index("status")
        await self.queue_collection.create_index("createdAt")
        await self.queue_collection.create_index("actorId")
        await self.queue_collection.create_index([("status", 1), ("createdAt", 1)])
        await self.bans_collection.create_index("actorId", unique=True)
        await self.bans_collection.create_index("expiresAt")
    
    def is_admin(self, telegram_id: int) -> bool:
        """Check if user is an admin"""
        return telegram_id in self.admin_ids
    
    async def submit_for_moderation(
        self,
        signal_id: str,
        actor_id: str,
        signal_type: str,
        text: str = None,
        photo_url: str = None,
        lat: float = None,
        lng: float = None,
        username: str = None
    ) -> Dict[str, Any]:
        """
        Submit a signal for moderation.
        Called when user submits a signal that requires review.
        """
        now = datetime.now(timezone.utc)
        
        doc = {
            "signalId": signal_id,
            "actorId": actor_id,
            "username": username,
            "signalType": signal_type,
            "text": text,
            "photoUrl": photo_url,
            "lat": lat,
            "lng": lng,
            "status": STATUS_PENDING,
            "createdAt": now,
            "updatedAt": now,
            "moderatedBy": None,
            "moderatedAt": None,
            "rejectionReason": None,
        }
        
        result = await self.queue_collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)
        
        logger.info(f"Signal submitted for moderation: {signal_id} by {actor_id}")
        
        # Notify admins
        await self._notify_admins_new_signal(doc)
        
        return {"ok": True, "queueId": str(result.inserted_id), "status": STATUS_PENDING}
    
    async def get_pending_count(self) -> int:
        """Get number of pending signals"""
        return await self.queue_collection.count_documents({"status": STATUS_PENDING})
    
    async def get_pending_signals(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get pending signals for moderation"""
        cursor = self.queue_collection.find(
            {"status": STATUS_PENDING},
            {"_id": 0}
        ).sort("createdAt", 1).limit(limit)
        
        return [doc async for doc in cursor]
    
    async def approve_signal(
        self,
        signal_id: str,
        admin_id: int,
        boost_confidence: bool = False
    ) -> Dict[str, Any]:
        """
        Approve a pending signal.
        Publishes the signal and updates trust score.
        """
        now = datetime.now(timezone.utc)
        
        # Find the queue item
        queue_item = await self.queue_collection.find_one({"signalId": signal_id})
        if not queue_item:
            return {"ok": False, "error": "Signal not found in queue"}
        
        if queue_item.get("status") != STATUS_PENDING:
            return {"ok": False, "error": f"Signal already {queue_item.get('status')}"}
        
        # Update queue status
        await self.queue_collection.update_one(
            {"signalId": signal_id},
            {
                "$set": {
                    "status": STATUS_APPROVED,
                    "moderatedBy": admin_id,
                    "moderatedAt": now,
                    "updatedAt": now
                }
            }
        )
        
        # Publish the signal (update tg_crowd_signals)
        confidence_boost = 0.2 if boost_confidence else 0
        await self.db.tg_crowd_signals.update_one(
            {"_id": queue_item.get("signalId")},
            {
                "$set": {
                    "status": "published",
                    "publishedAt": now,
                    "moderatedBy": admin_id
                },
                "$inc": {"confidence": confidence_boost}
            }
        )
        
        # Also publish to tg_geo_events if exists
        await self.db.tg_geo_events.update_one(
            {"signalId": signal_id},
            {
                "$set": {
                    "status": "active",
                    "publishedAt": now
                }
            }
        )
        
        # Update trust score
        from .trust_score_service import TrustScoreService
        trust_svc = TrustScoreService(self.db)
        await trust_svc.add_report(queue_item.get("actorId"), was_confirmed=True)
        
        logger.info(f"Signal approved: {signal_id} by admin {admin_id}")
        
        return {"ok": True, "action": "approved", "signalId": signal_id}
    
    async def reject_signal(
        self,
        signal_id: str,
        admin_id: int,
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Reject a pending signal.
        Removes/hides the signal and updates trust score.
        """
        now = datetime.now(timezone.utc)
        
        # Find the queue item
        queue_item = await self.queue_collection.find_one({"signalId": signal_id})
        if not queue_item:
            return {"ok": False, "error": "Signal not found in queue"}
        
        # Update queue status
        await self.queue_collection.update_one(
            {"signalId": signal_id},
            {
                "$set": {
                    "status": STATUS_REJECTED,
                    "moderatedBy": admin_id,
                    "moderatedAt": now,
                    "rejectionReason": reason,
                    "updatedAt": now
                }
            }
        )
        
        # Hide/remove the signal
        await self.db.tg_crowd_signals.update_one(
            {"_id": queue_item.get("signalId")},
            {
                "$set": {
                    "status": "rejected",
                    "rejectedAt": now,
                    "rejectionReason": reason,
                    "moderatedBy": admin_id
                }
            }
        )
        
        # Also update tg_geo_events
        await self.db.tg_geo_events.update_one(
            {"signalId": signal_id},
            {"$set": {"status": "rejected"}}
        )
        
        # Update trust score
        from .trust_score_service import TrustScoreService
        trust_svc = TrustScoreService(self.db)
        await trust_svc.add_report(queue_item.get("actorId"), was_confirmed=False)
        
        logger.info(f"Signal rejected: {signal_id} by admin {admin_id}, reason: {reason}")
        
        return {"ok": True, "action": "rejected", "signalId": signal_id}
    
    async def ban_user(
        self,
        actor_id: str,
        admin_id: int,
        duration: str = "short",
        reason: str = None
    ) -> Dict[str, Any]:
        """
        Ban a user from submitting signals.
        Duration: warning, short (24h), medium (7d), long (30d), permanent
        """
        now = datetime.now(timezone.utc)
        hours = BAN_DURATION_HOURS.get(duration, 24)
        
        if hours > 0:
            expires_at = now + timedelta(hours=hours)
        else:
            expires_at = None  # Warning, no actual ban
        
        if hours == 0:
            # Just a warning
            logger.info(f"Warning issued to {actor_id} by admin {admin_id}")
            return {"ok": True, "action": "warning", "actorId": actor_id}
        
        await self.bans_collection.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "actorId": actor_id,
                    "bannedBy": admin_id,
                    "bannedAt": now,
                    "expiresAt": expires_at,
                    "reason": reason,
                    "duration": duration
                }
            },
            upsert=True
        )
        
        logger.info(f"User banned: {actor_id} for {duration} by admin {admin_id}")
        
        return {
            "ok": True,
            "action": "banned",
            "actorId": actor_id,
            "duration": duration,
            "expiresAt": expires_at.isoformat() if expires_at else None
        }
    
    async def unban_user(self, actor_id: str, admin_id: int) -> Dict[str, Any]:
        """Remove ban from user"""
        result = await self.bans_collection.delete_one({"actorId": actor_id})
        
        if result.deleted_count > 0:
            logger.info(f"User unbanned: {actor_id} by admin {admin_id}")
            return {"ok": True, "action": "unbanned", "actorId": actor_id}
        
        return {"ok": False, "error": "User not banned"}
    
    async def is_user_banned(self, actor_id: str) -> Dict[str, Any]:
        """Check if user is currently banned"""
        now = datetime.now(timezone.utc)
        
        ban = await self.bans_collection.find_one({"actorId": actor_id})
        
        if not ban:
            return {"banned": False}
        
        expires_at = ban.get("expiresAt")
        
        if expires_at and now > expires_at:
            # Ban expired, remove it
            await self.bans_collection.delete_one({"actorId": actor_id})
            return {"banned": False}
        
        return {
            "banned": True,
            "reason": ban.get("reason"),
            "expiresAt": expires_at.isoformat() if expires_at else "permanent",
            "duration": ban.get("duration")
        }
    
    async def _notify_admins_new_signal(self, signal: Dict[str, Any]):
        """Send notification to admins about new signal pending moderation"""
        # This will be called from the bot service
        # Store notification for later pickup
        await self.db.geo_admin_notifications.insert_one({
            "type": "new_signal",
            "signalId": signal.get("signalId"),
            "actorId": signal.get("actorId"),
            "username": signal.get("username"),
            "signalType": signal.get("signalType"),
            "hasPhoto": bool(signal.get("photoUrl")),
            "createdAt": datetime.now(timezone.utc),
            "delivered": False
        })
    
    async def get_pending_admin_notifications(self) -> List[Dict[str, Any]]:
        """Get undelivered admin notifications"""
        cursor = self.db.geo_admin_notifications.find(
            {"delivered": False},
            {"_id": 0}
        ).sort("createdAt", 1).limit(50)
        
        return [doc async for doc in cursor]
    
    async def mark_notification_delivered(self, signal_id: str):
        """Mark notification as delivered"""
        await self.db.geo_admin_notifications.update_many(
            {"signalId": signal_id},
            {"$set": {"delivered": True}}
        )
    
    def format_moderation_message(self, signal: Dict[str, Any]) -> str:
        """Format signal for admin moderation message"""
        from .bot_keyboard_builder import EVENT_ICONS
        
        signal_type = signal.get("signalType", "unknown")
        icon = EVENT_ICONS.get(signal_type, "📍")
        username = signal.get("username", "Anonymous")
        text = signal.get("text", "")[:200]
        has_photo = "📷" if signal.get("photoUrl") else ""
        
        msg = (
            f"📩 *Новий сигнал*\n\n"
            f"Тип: {icon} {signal_type}\n"
            f"Користувач: @{username}\n"
        )
        
        if text:
            msg += f"Текст: {text}\n"
        
        if has_photo:
            msg += f"{has_photo} Є фото\n"
        
        if signal.get("lat") and signal.get("lng"):
            msg += f"📍 {signal['lat']:.5f}, {signal['lng']:.5f}\n"
        
        return msg
    
    def get_moderation_keyboard(self, signal_id: str) -> Dict[str, Any]:
        """Get inline keyboard for moderation actions"""
        return {
            "inline_keyboard": [
                [
                    {"text": "✔ Підтвердити", "callback_data": f"admin_approve:{signal_id}"},
                    {"text": "❌ Відхилити", "callback_data": f"admin_reject:{signal_id}"}
                ],
                [
                    {"text": "🚫 Забанити", "callback_data": f"admin_ban:{signal_id}"}
                ]
            ]
        }


# Admin IDs accessor
def get_admin_ids() -> List[int]:
    """Get list of admin Telegram IDs"""
    return ADMIN_IDS


def add_admin_id(telegram_id: int):
    """Add admin ID (runtime only, does not persist)"""
    if telegram_id not in ADMIN_IDS:
        ADMIN_IDS.append(telegram_id)
