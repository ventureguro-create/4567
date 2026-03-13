"""
Telegram Intel Module - Storage Layer
Version: 1.0.0

MongoDB collections and indexes for isolated storage.
All collections are prefixed with 'tg_' for namespace isolation.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)

# ============================================
# COLLECTION NAMES (FROZEN)
# ============================================

COLLECTIONS = {
    "channels": "tg_channel_states",
    "posts": "tg_posts", 
    "media": "tg_media_assets",
    "watchlist": "tg_watchlist",
    "feed_state": "tg_feed_state",
    "alerts": "tg_alerts",
    "alert_state": "tg_alert_state",
    "actor_links": "tg_actor_links",
    "delivery_outbox": "tg_delivery_outbox",
    "edge_events": "tg_edge_events",
    "members_history": "tg_members_history",
    "digest_state": "tg_digest_state",
}


async def ensure_indexes(db: AsyncIOMotorDatabase):
    """
    Create all required indexes for Telegram Intel collections.
    Safe to call multiple times.
    """
    try:
        # Channels
        await db[COLLECTIONS["channels"]].create_index("username", unique=True)
        await db[COLLECTIONS["channels"]].create_index("utilityScore")
        
        # Posts
        await db[COLLECTIONS["posts"]].create_index([("username", 1), ("messageId", 1)], unique=True)
        await db[COLLECTIONS["posts"]].create_index([("username", 1), ("date", -1)])
        await db[COLLECTIONS["posts"]].create_index("date")
        
        # Media
        await db[COLLECTIONS["media"]].create_index([("username", 1), ("messageId", 1)])
        
        # Watchlist
        await db[COLLECTIONS["watchlist"]].create_index([("actorId", 1), ("username", 1)], unique=True)
        
        # Feed state
        await db[COLLECTIONS["feed_state"]].create_index([("actorId", 1), ("postKey", 1)], unique=True)
        await db[COLLECTIONS["feed_state"]].create_index("isPinned")
        
        # Alerts
        await db[COLLECTIONS["alerts"]].create_index([("actorId", 1), ("createdAt", -1)])
        
        # Actor links
        await db[COLLECTIONS["actor_links"]].create_index([("actorId", 1), ("provider", 1)])
        
        # Delivery
        await db[COLLECTIONS["delivery_outbox"]].create_index("status")
        await db[COLLECTIONS["delivery_outbox"]].create_index("createdAt")
        
        # Edge events
        await db[COLLECTIONS["edge_events"]].create_index("source")
        await db[COLLECTIONS["edge_events"]].create_index("target")
        
        # Members history
        await db[COLLECTIONS["members_history"]].create_index([("username", 1), ("date", 1)])
        
        logger.info("Telegram Intel indexes initialized")
        return True
        
    except Exception as e:
        logger.error(f"Index creation failed: {e}")
        return False


class TelegramStorage:
    """
    Storage access layer for Telegram Intel.
    Provides type-safe access to all collections.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self._collections = COLLECTIONS
    
    @property
    def channels(self):
        return self.db[self._collections["channels"]]
    
    @property
    def posts(self):
        return self.db[self._collections["posts"]]
    
    @property
    def media(self):
        return self.db[self._collections["media"]]
    
    @property
    def watchlist(self):
        return self.db[self._collections["watchlist"]]
    
    @property
    def feed_state(self):
        return self.db[self._collections["feed_state"]]
    
    @property
    def alerts(self):
        return self.db[self._collections["alerts"]]
    
    @property
    def alert_state(self):
        return self.db[self._collections["alert_state"]]
    
    @property
    def actor_links(self):
        return self.db[self._collections["actor_links"]]
    
    @property
    def delivery_outbox(self):
        return self.db[self._collections["delivery_outbox"]]
    
    @property
    def edge_events(self):
        return self.db[self._collections["edge_events"]]
    
    @property
    def members_history(self):
        return self.db[self._collections["members_history"]]
    
    @property
    def digest_state(self):
        return self.db[self._collections["digest_state"]]
