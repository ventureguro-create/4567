"""
Risk Zone Repository - Database operations for dynamic risk zones
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class RiskZoneRepository:
    """Repository for tg_geo_risk_zones collection"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.tg_geo_risk_zones
    
    async def get_active_fused_events(self) -> List[Dict[str, Any]]:
        """Get all non-expired fused events"""
        cursor = self.db.tg_geo_fused_events.find({
            "status": {"$ne": "EXPIRED"}
        })
        return [x async for x in cursor]
    
    async def upsert_zone(self, zone: Dict[str, Any]):
        """Upsert a risk zone"""
        await self.collection.update_one(
            {"zoneId": zone["zoneId"]},
            {"$set": zone},
            upsert=True
        )
    
    async def get_active_zones(self) -> List[Dict[str, Any]]:
        """Get all active risk zones"""
        cursor = self.collection.find(
            {"status": "ACTIVE"},
            {"_id": 0}
        )
        return [x async for x in cursor]
    
    async def get_zones_near_location(
        self, 
        lat: float, 
        lng: float, 
        radius_m: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get risk zones near a location"""
        # Note: For proper geo queries, ensure 2dsphere index on center
        # Using simple distance calculation for now
        zones = await self.get_active_zones()
        
        from ..utils.geo_distance import haversine_distance
        
        result = []
        for zone in zones:
            coords = zone.get("center", {}).get("coordinates", [])
            if len(coords) >= 2:
                zone_lng, zone_lat = coords[0], coords[1]
                dist = haversine_distance(lat, lng, zone_lat, zone_lng)
                if dist <= radius_m + zone.get("radiusMeters", 300):
                    zone["distanceMeters"] = int(dist)
                    result.append(zone)
        
        return sorted(result, key=lambda x: x.get("distanceMeters", 0))
    
    async def expire_old_zones(self, max_age_minutes: int = 120):
        """Mark old zones as expired"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        result = await self.collection.update_many(
            {
                "status": "ACTIVE",
                "updatedAt": {"$lt": cutoff}
            },
            {"$set": {"status": "EXPIRED"}}
        )
        return result.modified_count
    
    async def delete_expired_zones(self):
        """Remove expired zones"""
        result = await self.collection.delete_many({"status": "EXPIRED"})
        return result.deleted_count


from datetime import timedelta
