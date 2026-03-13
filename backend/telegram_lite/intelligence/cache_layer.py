"""
Feed Cache Layer - Precomputed feed per actor
C1: Feed Cache Per Actor
C2: Precomputed Ranking Storage
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class FeedCacheRepository:
    """Repository for cached feed per actor"""
    
    def __init__(self, db):
        self.db = db
    
    async def get(self, actor_id: str) -> Optional[Dict]:
        """Get cached feed if not expired"""
        now = datetime.now(timezone.utc)
        
        return await self.db.tg_feed_cache.find_one({
            "actorId": actor_id,
            "expiresAt": {"$gt": now}
        })
    
    async def store(self, actor_id: str, items: List[Dict], ttl_minutes: int = 5):
        """Store computed feed with TTL"""
        now = datetime.now(timezone.utc)
        
        # Serialize items (remove non-serializable)
        serialized = []
        for item in items:
            clean = {k: v for k, v in item.items() if k != '_id'}
            serialized.append(clean)
        
        await self.db.tg_feed_cache.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "items": serialized,
                    "itemCount": len(serialized),
                    "calculatedAt": now,
                    "expiresAt": now + timedelta(minutes=ttl_minutes)
                }
            },
            upsert=True
        )
    
    async def invalidate(self, actor_id: str):
        """Invalidate cache for actor"""
        await self.db.tg_feed_cache.delete_one({"actorId": actor_id})


class TopicMomentumCacheRepository:
    """Repository for cached topic momentum (C3)"""
    
    def __init__(self, db):
        self.db = db
    
    async def get(self, window_hours: int = 6) -> Optional[Dict]:
        now = datetime.now(timezone.utc)
        
        return await self.db.tg_topic_momentum_cache.find_one({
            "windowHours": window_hours,
            "expiresAt": {"$gt": now}
        })
    
    async def store(self, window_hours: int, topics: List[Dict], ttl_minutes: int = 5):
        now = datetime.now(timezone.utc)
        
        await self.db.tg_topic_momentum_cache.update_one(
            {"windowHours": window_hours},
            {
                "$set": {
                    "topics": topics,
                    "calculatedAt": now,
                    "expiresAt": now + timedelta(minutes=ttl_minutes)
                }
            },
            upsert=True
        )


class AnomalyCacheRepository:
    """Repository for precomputed anomalies (C4)"""
    
    def __init__(self, db):
        self.db = db
    
    async def get(self, username: str, message_id: int) -> Optional[Dict]:
        return await self.db.tg_post_anomalies.find_one({
            "username": username,
            "messageId": message_id
        }, {"_id": 0})
    
    async def store(self, anomaly_data: Dict):
        now = datetime.now(timezone.utc)
        
        await self.db.tg_post_anomalies.update_one(
            {
                "username": anomaly_data["username"],
                "messageId": anomaly_data["messageId"]
            },
            {
                "$set": {
                    **anomaly_data,
                    "calculatedAt": now
                }
            },
            upsert=True
        )
    
    async def get_batch(self, keys: List[tuple]) -> Dict[tuple, Dict]:
        """Get multiple anomalies by (username, messageId) pairs"""
        if not keys:
            return {}
        
        or_filter = [{"username": k[0], "messageId": k[1]} for k in keys]
        cursor = self.db.tg_post_anomalies.find({"$or": or_filter}, {"_id": 0})
        
        result = {}
        async for doc in cursor:
            key = (doc["username"], doc["messageId"])
            result[key] = doc
        
        return result


async def ensure_cache_indexes(db):
    """Create indexes for cache collections"""
    try:
        # Feed cache
        await db.tg_feed_cache.create_index([("actorId", 1)], unique=True)
        await db.tg_feed_cache.create_index([("expiresAt", 1)], expireAfterSeconds=0)
        
        # Topic momentum cache
        await db.tg_topic_momentum_cache.create_index([("windowHours", 1)])
        await db.tg_topic_momentum_cache.create_index([("expiresAt", 1)], expireAfterSeconds=0)
        
        # Anomaly cache
        await db.tg_post_anomalies.create_index([("username", 1), ("messageId", 1)], unique=True)
        await db.tg_post_anomalies.create_index([("calculatedAt", 1)])
        
        logger.info("Cache indexes created")
    except Exception as e:
        logger.warning(f"Cache index warning: {e}")
