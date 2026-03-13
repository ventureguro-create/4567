"""
Bot Location Service - Manage user locations
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class BotLocationService:
    """Service for managing user locations"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_bot_locations
    
    async def update_location(
        self, 
        actor_id: str, 
        lat: float, 
        lng: float,
        is_live: bool = False
    ) -> Dict[str, Any]:
        """Update user location"""
        now = datetime.now(timezone.utc)
        
        doc = {
            "actorId": actor_id,
            "lat": lat,
            "lng": lng,
            "isLive": is_live,
            "updatedAt": now
        }
        
        await self.collection.update_one(
            {"actorId": actor_id},
            {"$set": doc},
            upsert=True
        )
        
        logger.info(f"Updated location for {actor_id}: {lat}, {lng}")
        
        return {"ok": True, "lat": lat, "lng": lng, "updatedAt": now}
    
    async def get_location(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """Get user location"""
        return await self.collection.find_one({"actorId": actor_id}, {"_id": 0})
    
    async def get_location_age_minutes(self, actor_id: str) -> Optional[float]:
        """Get how old the location is in minutes"""
        loc = await self.get_location(actor_id)
        if not loc:
            return None
        
        updated = loc.get("updatedAt")
        if not updated:
            return None
        
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        
        age = datetime.now(timezone.utc) - updated
        return age.total_seconds() / 60
    
    async def has_recent_location(self, actor_id: str, max_age_minutes: int = 60) -> bool:
        """Check if user has a recent location"""
        age = await self.get_location_age_minutes(actor_id)
        if age is None:
            return False
        return age <= max_age_minutes
    
    async def get_users_with_location(self) -> List[Dict[str, Any]]:
        """Get all users who have set a location"""
        cursor = self.collection.find({}, {"_id": 0})
        return [doc async for doc in cursor]
    
    async def get_active_locations(self, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """Get locations updated within specified hours"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cursor = self.collection.find(
            {"updatedAt": {"$gte": cutoff}},
            {"_id": 0}
        )
        return [doc async for doc in cursor]
    
    async def delete_location(self, actor_id: str) -> bool:
        """Delete user location"""
        result = await self.collection.delete_one({"actorId": actor_id})
        return result.deleted_count > 0
