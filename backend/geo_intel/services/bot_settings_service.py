"""
Bot Settings Service - Manage user radar settings
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_SETTINGS = {
    "radarEnabled": False,
    "radius": 1000,
    "eventTypes": ["virus", "trash", "rain", "heavy_rain"],
    "summaryEnabled": True,
    "language": "uk",
    "quietHours": {
        "enabled": False,
        "from": 23,
        "to": 7
    },
    "sensitivity": "medium",  # low, medium, high
}

RADIUS_OPTIONS = [500, 1000, 2000, 3000]
SENSITIVITY_OPTIONS = ["low", "medium", "high"]
EVENT_TYPES = ["virus", "trash", "rain", "heavy_rain"]


class BotSettingsService:
    """Service for managing user settings"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_bot_settings
    
    async def get_or_create_settings(self, actor_id: str) -> Dict[str, Any]:
        """Get existing settings or create defaults"""
        existing = await self.collection.find_one({"actorId": actor_id})
        
        if existing:
            return {**existing, "_id": None}
        
        # Create default settings
        now = datetime.now(timezone.utc)
        doc = {
            "actorId": actor_id,
            **DEFAULT_SETTINGS,
            "createdAt": now,
            "updatedAt": now
        }
        
        await self.collection.insert_one(doc)
        logger.info(f"Created default settings for: {actor_id}")
        
        return {**doc, "_id": None}
    
    async def get_settings(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """Get user settings"""
        return await self.collection.find_one({"actorId": actor_id}, {"_id": 0})
    
    async def update_settings(self, actor_id: str, updates: Dict[str, Any]) -> bool:
        """Update settings"""
        updates["updatedAt"] = datetime.now(timezone.utc)
        
        result = await self.collection.update_one(
            {"actorId": actor_id},
            {"$set": updates},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None
    
    async def set_radar_enabled(self, actor_id: str, enabled: bool) -> bool:
        """Enable/disable radar"""
        return await self.update_settings(actor_id, {"radarEnabled": enabled})
    
    async def set_radius(self, actor_id: str, radius: int) -> bool:
        """Set radar radius"""
        if radius not in RADIUS_OPTIONS:
            radius = 1000  # default
        return await self.update_settings(actor_id, {"radius": radius})
    
    async def set_event_types(self, actor_id: str, event_types: List[str]) -> bool:
        """Set event types to monitor"""
        valid_types = [t for t in event_types if t in EVENT_TYPES]
        return await self.update_settings(actor_id, {"eventTypes": valid_types})
    
    async def toggle_event_type(self, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Toggle single event type on/off"""
        if event_type not in EVENT_TYPES:
            return {"ok": False, "error": "Invalid event type"}
        
        settings = await self.get_or_create_settings(actor_id)
        current_types = settings.get("eventTypes", [])
        
        if event_type in current_types:
            current_types.remove(event_type)
        else:
            current_types.append(event_type)
        
        await self.update_settings(actor_id, {"eventTypes": current_types})
        
        return {"ok": True, "eventTypes": current_types, "toggled": event_type}
    
    async def set_sensitivity(self, actor_id: str, sensitivity: str) -> bool:
        """Set alert sensitivity"""
        if sensitivity not in SENSITIVITY_OPTIONS:
            sensitivity = "medium"
        return await self.update_settings(actor_id, {"sensitivity": sensitivity})
    
    async def set_quiet_hours(
        self, 
        actor_id: str, 
        enabled: bool,
        from_hour: int = 23,
        to_hour: int = 7
    ) -> bool:
        """Set quiet hours"""
        return await self.update_settings(actor_id, {
            "quietHours": {
                "enabled": enabled,
                "from": from_hour,
                "to": to_hour
            }
        })
    
    async def get_users_with_radar_enabled(self) -> List[Dict[str, Any]]:
        """Get all users with radar enabled"""
        cursor = self.collection.find(
            {"radarEnabled": True},
            {"_id": 0}
        )
        return [doc async for doc in cursor]
