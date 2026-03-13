"""
Fusion Repository
Database operations for fused events
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional


class FusionRepository:
    def __init__(self, db):
        self.db = db
    
    async def get_recent_raw_events(self, minutes: int = 30) -> List[Dict]:
        """Get raw events from last N minutes"""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        cursor = self.db.tg_geo_events.find(
            {"createdAt": {"$gte": since}},
            {"_id": 0}
        )
        return await cursor.to_list(1000)
    
    async def upsert_fused_event(self, doc: Dict):
        """Insert or update fused event"""
        await self.db.tg_geo_fused_events.update_one(
            {"fusedId": doc["fusedId"]},
            {"$set": doc},
            upsert=True
        )
    
    async def get_active_fused_events(self) -> List[Dict]:
        """Get all non-expired fused events"""
        cursor = self.db.tg_geo_fused_events.find(
            {"status": {"$in": ["NEW", "CONFIRMED", "ACTIVE", "DECAYING"]}},
            {"_id": 0}
        )
        return await cursor.to_list(1000)
    
    async def get_fused_event(self, fused_id: str) -> Optional[Dict]:
        """Get single fused event"""
        return await self.db.tg_geo_fused_events.find_one(
            {"fusedId": fused_id},
            {"_id": 0}
        )
    
    async def expire_old_events(self, older_than_minutes: int = 180):
        """Mark old events as expired"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        result = await self.db.tg_geo_fused_events.update_many(
            {
                "status": {"$ne": "EXPIRED"},
                "lastSeenAt": {"$lt": cutoff}
            },
            {"$set": {"status": "EXPIRED"}}
        )
        return result.modified_count
