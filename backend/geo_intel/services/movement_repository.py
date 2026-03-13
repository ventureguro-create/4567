"""
Movement Repository - Database operations for movement tracking
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class MovementRepository:
    """Repository for tg_geo_movements collection"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.tg_geo_movements
    
    async def get_recent_fused_events(self, hours: int = 6) -> List[Dict[str, Any]]:
        """Get recent fused events for movement detection"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cursor = self.db.tg_geo_fused_events.find({
            "status": {"$ne": "EXPIRED"},
            "lastSeenAt": {"$gte": cutoff}
        }).sort("lastSeenAt", 1)
        return [x async for x in cursor]
    
    async def upsert_movement(self, doc: Dict[str, Any]):
        """Upsert a movement"""
        await self.collection.update_one(
            {"movementId": doc["movementId"]},
            {"$set": doc},
            upsert=True
        )
    
    async def get_active_movements(self) -> List[Dict[str, Any]]:
        """Get all active movements"""
        cursor = self.collection.find(
            {"status": "ACTIVE"},
            {"_id": 0}
        )
        return [x async for x in cursor]
    
    async def get_movements_near_location(
        self, 
        lat: float, 
        lng: float, 
        radius_m: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get movements that pass near a location"""
        from ..utils.geo_distance import haversine_distance
        
        movements = await self.get_active_movements()
        
        result = []
        for m in movements:
            points = m.get("points", [])
            if not points:
                continue
            
            # Check if any point is within radius
            min_dist = float('inf')
            for p in points:
                dist = haversine_distance(lat, lng, p["lat"], p["lng"])
                min_dist = min(min_dist, dist)
            
            if min_dist <= radius_m:
                m["minDistanceMeters"] = int(min_dist)
                result.append(m)
        
        return sorted(result, key=lambda x: x.get("minDistanceMeters", 0))
    
    async def expire_old_movements(self, max_age_hours: int = 3):
        """Mark old movements as expired"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        result = await self.collection.update_many(
            {
                "status": "ACTIVE",
                "updatedAt": {"$lt": cutoff}
            },
            {"$set": {"status": "EXPIRED"}}
        )
        return result.modified_count
    
    async def delete_expired_movements(self):
        """Remove expired movements"""
        result = await self.collection.delete_many({"status": "EXPIRED"})
        return result.deleted_count
