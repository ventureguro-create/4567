"""
Alert Engine v2 - Final Production Version
Only 4 types: ANOMALY, CROSS_CHANNEL, CHANNEL_EVENT, DIGEST
Rate controlled, preference-aware, no spam
"""
import datetime as dt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# =========================
# CONFIG - FINAL
# =========================

MAX_ALERTS_PER_HOUR = 3
MAX_ALERTS_PER_DAY = 8

PRIORITY = {
    "ANOMALY": 3,
    "CROSS_CHANNEL": 2,
    "CHANNEL_EVENT": 2,
    "DIGEST": 1
}

# =========================
# ENGINE
# =========================

class AlertEngineV2:
    """
    Production Alert Engine
    - Only sends analytical signals (no post forwarding)
    - Rate limited per actor
    - Preference-aware
    """

    def __init__(self, db, bot_sender: Optional[Callable] = None):
        """
        db: MongoDB async client
        bot_sender: async function(chat_id: str, text: str) -> None
        """
        self.db = db
        self.bot_sender = bot_sender

    # =====================================
    # PUBLIC ENTRY
    # =====================================

    async def dispatch(self, actor_id: str, alert: Dict[str, Any]) -> bool:
        """
        Main entry point. Returns True if alert was sent.
        """
        alert_type = alert.get("type", "UNKNOWN")
        
        # Check rate limits and preferences
        if not await self._should_send(actor_id, alert):
            logger.debug(f"Alert {alert_type} blocked for {actor_id} (rate limit or preference)")
            return False

        # Format message
        formatted = self._format(alert)
        
        # Send via bot if available
        sent = False
        if self.bot_sender:
            chat_id = await self._get_actor_chat_id(actor_id)
            if chat_id:
                try:
                    await self.bot_sender(chat_id, formatted)
                    sent = True
                    logger.info(f"Alert {alert_type} sent to {actor_id}")
                except Exception as e:
                    logger.error(f"Bot send failed: {e}")
        
        # Always record alert (even if not sent via bot)
        await self._record_alert(actor_id, alert, sent)
        
        return sent

    async def dispatch_to_all_watchers(self, alert: Dict[str, Any]) -> int:
        """
        Dispatch alert to all actors watching relevant channel/topic
        Returns count of alerts sent
        """
        sent_count = 0
        
        # Get actors based on alert type
        actors = []
        if alert["type"] == "ANOMALY":
            channel = alert.get("channel", "")
            actors = await self._get_actors_watching_channel(channel)
        elif alert["type"] == "CROSS_CHANNEL":
            # All active actors
            actors = await self._get_active_actors()
        
        for actor_id in actors:
            if await self.dispatch(actor_id, alert):
                sent_count += 1
        
        return sent_count

    # =====================================
    # RATE LIMIT CONTROL
    # =====================================

    async def _should_send(self, actor_id: str, alert: Dict[str, Any]) -> bool:
        now = datetime.now(timezone.utc)
        alert_type = alert.get("type", "").lower()

        # Get actor settings
        settings = await self.db.actor_settings.find_one({"actorId": actor_id}) or {}
        alerts_config = settings.get("alerts", {})
        
        # Check if this alert type is enabled
        if not alerts_config.get(alert_type, True):
            return False

        # Hour limit
        hour_ago = now - timedelta(hours=1)
        count_hour = await self.db.alert_logs.count_documents({
            "actorId": actor_id,
            "createdAt": {"$gte": hour_ago}
        })

        if count_hour >= MAX_ALERTS_PER_HOUR:
            logger.debug(f"Hour limit reached for {actor_id}")
            return False

        # Day limit
        day_ago = now - timedelta(days=1)
        count_day = await self.db.alert_logs.count_documents({
            "actorId": actor_id,
            "createdAt": {"$gte": day_ago}
        })

        max_per_day = settings.get("maxPerDay", MAX_ALERTS_PER_DAY)
        if count_day >= max_per_day:
            logger.debug(f"Day limit reached for {actor_id}")
            return False

        return True

    # =====================================
    # FORMATTERS
    # =====================================

    def _format(self, alert: Dict[str, Any]) -> str:
        t = alert.get("type", "")

        if t == "ANOMALY":
            return self._format_anomaly(alert)
        if t == "CROSS_CHANNEL":
            return self._format_cross(alert)
        if t == "CHANNEL_EVENT":
            return self._format_channel_event(alert)
        if t == "DIGEST":
            return self._format_digest(alert)

        return f"Unknown alert type: {t}"

    def _format_anomaly(self, alert: Dict[str, Any]) -> str:
        metrics = alert.get("metrics", {})
        return f"""🚨 ANOMALY DETECTED

Channel: {alert.get('channel', 'Unknown')}
Post ID: {alert.get('messageId', '?')}
Score: {round(alert.get('anomalyScore', 0), 2)}

Views: {metrics.get('views', 0):,}
Forwards: {metrics.get('forwards', 0):,}
Replies Z-Score: {round(metrics.get('repliesZ', 0), 2)}

⚡ This post is performing above channel average.

Open in Telegram:
{alert.get('telegramUrl', '')}"""

    def _format_cross(self, alert: Dict[str, Any]) -> str:
        channels = alert.get("channels", [])
        channels_list = "\n".join([f"• {c}" for c in channels[:6]])
        if len(channels) > 6:
            channels_list += f"\n• +{len(channels) - 6} more"

        return f"""🔥 CROSS-CHANNEL SIGNAL

Topic: {alert.get('topic', 'Unknown')}
Channels: {len(channels)}
Window: {alert.get('windowMinutes', 60)} minutes

Mentioned by:
{channels_list}

Momentum Score: {round(alert.get('momentumScore', 0), 2)}

This topic is trending across your watchlist."""

    def _format_channel_event(self, alert: Dict[str, Any]) -> str:
        return f"""📊 CHANNEL EVENT

{alert.get('channel', 'Unknown')}
+{round(alert.get('growth7', 0), 2)}% growth (7d)

Anomalies: {alert.get('anomalyCount', 0)} in last 24h
Engagement: {round(alert.get('engagementMultiplier', 1), 1)}x

This channel is accelerating."""

    def _format_digest(self, alert: Dict[str, Any]) -> str:
        topics = alert.get("topTopics", [])
        topics_list = "\n".join([f"• {t}" for t in topics[:5]])

        return f"""🧠 DAILY DIGEST

Top Topics:
{topics_list}

Most Active: {alert.get('mostActiveChannel', 'N/A')}
Trending: {alert.get('trendingAsset', 'N/A')}

Summary:
{alert.get('summary', 'No summary available.')}"""

    # =====================================
    # HELPERS
    # =====================================

    async def _get_actor_chat_id(self, actor_id: str) -> Optional[str]:
        """Get Telegram chat ID for actor"""
        actor = await self.db.tg_actors.find_one({"actorId": actor_id})
        return actor.get("telegramChatId") if actor else None

    async def _get_actors_watching_channel(self, channel: str) -> List[str]:
        """Get actors who have channel in watchlist"""
        watchlist = await self.db.tg_watchlist.find(
            {"username": channel.lower()},
            {"actorId": 1}
        ).to_list(100)
        return [w.get("actorId") for w in watchlist if w.get("actorId")]

    async def _get_active_actors(self) -> List[str]:
        """Get all active actors"""
        actors = await self.db.tg_actors.find(
            {"active": {"$ne": False}},
            {"actorId": 1}
        ).to_list(100)
        return [a.get("actorId") for a in actors if a.get("actorId")]

    # =====================================
    # LOGGING
    # =====================================

    async def _record_alert(self, actor_id: str, alert: Dict[str, Any], sent: bool):
        """Record alert in log for rate limiting"""
        await self.db.alert_logs.insert_one({
            "actorId": actor_id,
            "type": alert.get("type"),
            "priority": PRIORITY.get(alert.get("type"), 1),
            "sent": sent,
            "createdAt": datetime.now(timezone.utc),
            "meta": {k: v for k, v in alert.items() if k != "type"}
        })


# =========================
# ALERT BUILDERS
# =========================

def build_anomaly_alert(
    channel: str,
    message_id: int,
    anomaly_score: float,
    views: int,
    forwards: int,
    replies_z: float
) -> Dict[str, Any]:
    """Build ANOMALY alert payload"""
    return {
        "type": "ANOMALY",
        "channel": channel,
        "messageId": message_id,
        "anomalyScore": anomaly_score,
        "metrics": {
            "views": views,
            "forwards": forwards,
            "repliesZ": replies_z
        },
        "telegramUrl": f"https://t.me/{channel}/{message_id}"
    }


def build_cross_channel_alert(
    topic: str,
    channels: List[str],
    window_minutes: int,
    momentum_score: float
) -> Dict[str, Any]:
    """Build CROSS_CHANNEL alert payload"""
    return {
        "type": "CROSS_CHANNEL",
        "topic": topic,
        "channels": channels,
        "windowMinutes": window_minutes,
        "momentumScore": momentum_score
    }


def build_channel_event_alert(
    channel: str,
    growth7: float,
    anomaly_count: int = 0,
    engagement_multiplier: float = 1.0
) -> Dict[str, Any]:
    """Build CHANNEL_EVENT alert payload"""
    return {
        "type": "CHANNEL_EVENT",
        "channel": channel,
        "growth7": growth7,
        "anomalyCount": anomaly_count,
        "engagementMultiplier": engagement_multiplier
    }


def build_digest_alert(
    top_topics: List[str],
    most_active_channel: str,
    trending_asset: str,
    summary: str
) -> Dict[str, Any]:
    """Build DIGEST alert payload"""
    return {
        "type": "DIGEST",
        "topTopics": top_topics,
        "mostActiveChannel": most_active_channel,
        "trendingAsset": trending_asset,
        "summary": summary
    }


# =========================
# INDEXES
# =========================

async def ensure_alert_v2_indexes(db):
    """Create indexes for alert system"""
    try:
        await db.alert_logs.create_index([("actorId", 1), ("createdAt", -1)])
        await db.alert_logs.create_index([("createdAt", 1)], expireAfterSeconds=30*24*3600)  # 30 day TTL
        await db.actor_settings.create_index([("actorId", 1)], unique=True)
        logger.info("Alert v2 indexes created")
    except Exception as e:
        logger.warning(f"Alert v2 index warning: {e}")


# =========================
# LEGACY COMPATIBILITY CLASSES
# =========================

class Alert:
    """Legacy Alert data class"""
    def __init__(self, alert_type: str, actor_id: str, channel: str = None, 
                 message_id: int = None, data: dict = None):
        self.type = alert_type
        self.actor_id = actor_id
        self.channel = channel
        self.message_id = message_id
        self.data = data or {}
        self.created_at = datetime.now(timezone.utc)


class AlertRepository:
    """Repository for alerts storage and retrieval"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.alert_logs
    
    async def save(self, alert: dict) -> str:
        """Save alert to database"""
        result = await self.collection.insert_one(alert)
        return str(result.inserted_id)
    
    async def get_recent(self, actor_id: str, hours: int = 24, limit: int = 50) -> list:
        """Get recent alerts for actor"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        cursor = self.collection.find(
            {"actorId": actor_id, "createdAt": {"$gte": since}},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit)
        
        return await cursor.to_list(limit)
    
    async def count_in_window(self, actor_id: str, hours: int = 1) -> int:
        """Count alerts in time window"""
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        return await self.collection.count_documents({
            "actorId": actor_id,
            "createdAt": {"$gte": since}
        })


class AlertPreferencesRepository:
    """Repository for alert preferences"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.actor_settings
    
    async def get(self, actor_id: str) -> dict:
        """Get preferences for actor"""
        prefs = await self.collection.find_one(
            {"actorId": actor_id},
            {"_id": 0}
        )
        return prefs or {
            "actorId": actor_id,
            "alerts": {
                "anomaly": True,
                "cross_channel": True,
                "channel_event": True,
                "digest": True
            },
            "maxPerDay": MAX_ALERTS_PER_DAY
        }
    
    async def update(self, actor_id: str, prefs: dict) -> bool:
        """Update preferences for actor"""
        await self.collection.update_one(
            {"actorId": actor_id},
            {"$set": {**prefs, "actorId": actor_id, "updatedAt": datetime.now(timezone.utc)}},
            upsert=True
        )
        return True


class AlertPreferencesService:
    """Service for managing alert preferences"""
    
    def __init__(self, repo: AlertPreferencesRepository):
        self.repo = repo
    
    async def get_preferences(self, actor_id: str) -> dict:
        return await self.repo.get(actor_id)
    
    async def update_preferences(self, actor_id: str, prefs: dict) -> bool:
        return await self.repo.update(actor_id, prefs)


class AlertCooldownManager:
    """Manages alert cooldowns"""
    
    def __init__(self, db):
        self.db = db
    
    async def can_send(self, actor_id: str) -> bool:
        """Check if alert can be sent (cooldown check)"""
        repo = AlertRepository(self.db)
        count_hour = await repo.count_in_window(actor_id, hours=1)
        count_day = await repo.count_in_window(actor_id, hours=24)
        
        return count_hour < MAX_ALERTS_PER_HOUR and count_day < MAX_ALERTS_PER_DAY


class AlertEventBus:
    """Event bus for alert notifications"""
    pass


class AlertCore:
    """Core alert engine"""
    
    def __init__(self, db, bot_sender=None):
        self.db = db
        self.bot_sender = bot_sender
        self.engine = AlertEngineV2(db, bot_sender)
    
    async def send_alert(self, actor_id: str, alert_type: str, data: dict) -> bool:
        """Send alert to actor"""
        alert = {
            "type": alert_type,
            **data
        }
        return await self.engine.dispatch(actor_id, alert)


class WebAlertChannel:
    """Web push alert channel"""
    pass


class TelegramAlertChannel:
    """Telegram bot alert channel"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token


async def ensure_alert_indexes(db):
    """Alias for ensure_alert_v2_indexes"""
    await ensure_alert_v2_indexes(db)

