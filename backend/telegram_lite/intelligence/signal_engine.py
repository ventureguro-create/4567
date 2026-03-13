"""
Cross-Channel Signal Engine - Detect coordinated market events
When 3+ channels mention same topic within short window → Market Event
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SignalRepository:
    """Repository for cross-channel signal aggregation"""
    
    def __init__(self, db):
        self.db = db
    
    async def aggregate_topic_window(self, minutes: int = 30) -> List[Dict]:
        """Find topics mentioned by multiple channels in time window"""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        since_str = since.isoformat()
        
        pipeline = [
            {"$match": {
                "date": {"$gte": since_str},
                "extractedTopics": {"$exists": True, "$ne": []}
            }},
            {"$unwind": "$extractedTopics"},
            {"$group": {
                "_id": "$extractedTopics",
                "channels": {"$addToSet": "$username"},
                "mentions": {"$sum": 1}
            }},
            {"$project": {
                "topic": "$_id",
                "channels": 1,
                "mentions": 1,
                "channelCount": {"$size": "$channels"}
            }},
            {"$match": {"channelCount": {"$gte": 2}}},  # At least 2 channels
            {"$sort": {"channelCount": -1, "mentions": -1}},
            {"$limit": 30}
        ]
        
        return await self.db.tg_posts.aggregate(pipeline).to_list(30)


class SignalCacheRepository:
    """Repository for caching computed signals"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_cached(self, window_minutes: int) -> Dict:
        """Get cached signals if not expired"""
        now = datetime.now(timezone.utc)
        
        return await self.db.tg_cross_channel_signals.find_one({
            "windowMinutes": window_minutes,
            "expiresAt": {"$gt": now}
        })
    
    async def store(self, window_minutes: int, events: List, ttl_minutes: int = 5):
        """Store computed signals with TTL"""
        now = datetime.now(timezone.utc)
        
        await self.db.tg_cross_channel_signals.update_one(
            {"windowMinutes": window_minutes},
            {
                "$set": {
                    "events": events,
                    "calculatedAt": now,
                    "expiresAt": now + timedelta(minutes=ttl_minutes)
                }
            },
            upsert=True
        )


class CrossChannelSignalEngine:
    """Detect cross-channel market events"""
    
    def __init__(self, repo: SignalRepository):
        self.repo = repo
    
    async def detect(self, window_minutes: int = 30) -> List[Dict[str, Any]]:
        """Detect cross-channel events"""
        
        raw = await self.repo.aggregate_topic_window(window_minutes)
        
        events = []
        
        for item in raw:
            channels = item.get("channels", [])
            channel_count = len(channels)
            mentions = item.get("mentions", 0)
            
            # Event score based on coverage and volume
            event_score = round(channel_count * 1.5 + mentions * 0.5, 2)
            
            # Strong signal if many channels or high volume
            is_strong = channel_count >= 3 or mentions >= 5
            
            events.append({
                "topic": item.get("topic"),
                "channels": channels,
                "channelCount": channel_count,
                "mentions": mentions,
                "windowMinutes": window_minutes,
                "eventScore": event_score,
                "isStrongSignal": is_strong
            })
        
        return events


class CrossChannelSignalService:
    """Service with caching for cross-channel signals"""
    
    def __init__(self, db):
        self.db = db
        self.repo = SignalRepository(db)
        self.cache = SignalCacheRepository(db)
        self.engine = CrossChannelSignalEngine(self.repo)
    
    async def get_signals(self, window_minutes: int = 30, force_refresh: bool = False) -> List[Dict]:
        """Get signals from cache or compute fresh"""
        
        if not force_refresh:
            cached = await self.cache.get_cached(window_minutes)
            if cached:
                return cached.get("events", [])
        
        # Compute fresh
        events = await self.engine.detect(window_minutes)
        
        # Cache for 5 minutes
        await self.cache.store(window_minutes, events, ttl_minutes=5)
        
        return events


async def ensure_signal_indexes(db):
    """Create indexes for signal system"""
    try:
        await db.tg_cross_channel_signals.create_index([("windowMinutes", 1)])
        await db.tg_cross_channel_signals.create_index(
            [("expiresAt", 1)],
            expireAfterSeconds=0  # TTL index
        )
        logger.info("Signal indexes created")
    except Exception as e:
        logger.warning(f"Signal index warning: {e}")
