"""
Geo Session Service
Manages user geo sessions with TTL (privacy-first approach)
User controls how long their location is stored
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from .cell_encoder import get_cells_for_radius, round_location, haversine_distance

logger = logging.getLogger(__name__)

# TTL modes
SESSION_MODES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "1d": 1440,  # 24 hours
    "permanent": 1440,  # 24h with auto-refresh reminder
    "none": 0,  # Don't store
}

# Mode labels for UI
MODE_LABELS = {
    "5m": "5 хвилин",
    "15m": "15 хвилин",
    "1h": "1 година",
    "1d": "1 день",
    "permanent": "Постійно",
    "none": "Не зберігати",
}

# Default radius buckets
RADIUS_OPTIONS = [500, 1000, 2000, 5000]


class GeoSessionService:
    """Manages geo sessions with TTL"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_sessions
    
    async def create_session(
        self,
        user_id: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        mode: str = "15m",
        precision_meters: int = 100
    ) -> Dict[str, Any]:
        """
        Create or update geo session
        
        Args:
            user_id: User identifier (e.g., tg_123456)
            lat, lng: Location coordinates
            radius: Alert radius in meters
            mode: TTL mode (5m, 15m, 1h, 1d, permanent, none)
            precision_meters: Location rounding for privacy
        
        Returns:
            Session document
        """
        now = datetime.now(timezone.utc)
        
        # Don't store if mode is "none"
        if mode == "none":
            await self.delete_session(user_id)
            return {
                "userId": user_id,
                "mode": "none",
                "stored": False
            }
        
        # Round location for privacy
        rounded_lat, rounded_lng = round_location(lat, lng, precision_meters)
        
        # Get cell data for fast matching
        cell_data = get_cells_for_radius(rounded_lat, rounded_lng, radius)
        
        # Calculate expiration
        ttl_minutes = SESSION_MODES.get(mode, 15)
        expires_at = now + timedelta(minutes=ttl_minutes)
        
        # Build session document
        session = {
            "userId": user_id,
            "lat": rounded_lat,
            "lng": rounded_lng,
            "originalLat": lat,  # Keep original for exact matching
            "originalLng": lng,
            "radius": radius,
            "radiusBucket": cell_data["radiusBucket"],
            "cell": cell_data["cell"],
            "neighborCells": cell_data["neighbors"],
            "precision": cell_data["precision"],
            "mode": mode,
            "ttlMinutes": ttl_minutes,
            "isActive": True,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": expires_at,
            "lastAlertAt": None,
            "alertCount": 0
        }
        
        # Upsert session
        await self.collection.update_one(
            {"userId": user_id},
            {"$set": session},
            upsert=True
        )
        
        logger.info(f"Geo session created: {user_id}, mode={mode}, cell={cell_data['cell']}")
        
        return session
    
    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's active session"""
        now = datetime.now(timezone.utc)
        
        session = await self.collection.find_one(
            {
                "userId": user_id,
                "isActive": True,
                "expiresAt": {"$gt": now}
            },
            {"_id": 0}
        )
        
        return session
    
    async def extend_session(self, user_id: str, additional_minutes: int) -> Optional[Dict[str, Any]]:
        """Extend session TTL"""
        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(minutes=additional_minutes)
        
        result = await self.collection.find_one_and_update(
            {"userId": user_id, "isActive": True},
            {
                "$set": {
                    "expiresAt": new_expires,
                    "updatedAt": now
                }
            },
            return_document=True
        )
        
        if result:
            logger.info(f"Session extended: {user_id} +{additional_minutes}min")
        
        return result
    
    async def delete_session(self, user_id: str) -> bool:
        """Delete/deactivate session"""
        result = await self.collection.update_one(
            {"userId": user_id},
            {"$set": {"isActive": False, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Session deleted: {user_id}")
            return True
        return False
    
    async def get_sessions_in_cells(self, cells: List[str]) -> List[Dict[str, Any]]:
        """
        Find all active sessions in given cells
        This is the fast path for event matching
        """
        now = datetime.now(timezone.utc)
        
        sessions = await self.collection.find(
            {
                "isActive": True,
                "expiresAt": {"$gt": now},
                "$or": [
                    {"cell": {"$in": cells}},
                    {"neighborCells": {"$elemMatch": {"$in": cells}}}
                ]
            },
            {"_id": 0}
        ).to_list(1000)
        
        return sessions
    
    async def get_expiring_sessions(self, minutes: int = 1) -> List[Dict[str, Any]]:
        """Get sessions expiring within N minutes"""
        now = datetime.now(timezone.utc)
        threshold = now + timedelta(minutes=minutes)
        
        sessions = await self.collection.find(
            {
                "isActive": True,
                "expiresAt": {"$gt": now, "$lt": threshold}
            },
            {"_id": 0}
        ).to_list(100)
        
        return sessions
    
    async def get_permanent_sessions_needing_refresh(self) -> List[Dict[str, Any]]:
        """Get permanent sessions that need daily refresh reminder"""
        now = datetime.now(timezone.utc)
        
        sessions = await self.collection.find(
            {
                "isActive": True,
                "mode": "permanent",
                "expiresAt": {"$lt": now + timedelta(hours=1)}
            },
            {"_id": 0}
        ).to_list(100)
        
        return sessions
    
    async def update_last_alert(self, user_id: str) -> None:
        """Update last alert timestamp"""
        await self.collection.update_one(
            {"userId": user_id},
            {
                "$set": {"lastAlertAt": datetime.now(timezone.utc)},
                "$inc": {"alertCount": 1}
            }
        )
    
    async def get_session_stats(self) -> Dict[str, Any]:
        """Get aggregated session statistics (for admin)"""
        now = datetime.now(timezone.utc)
        
        pipeline = [
            {"$match": {"isActive": True, "expiresAt": {"$gt": now}}},
            {
                "$group": {
                    "_id": "$mode",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        results = await self.collection.aggregate(pipeline).to_list(10)
        
        stats = {
            "totalActive": 0,
            "byMode": {}
        }
        
        for r in results:
            stats["byMode"][r["_id"]] = r["count"]
            stats["totalActive"] += r["count"]
        
        return stats
    
    async def cleanup_expired(self) -> int:
        """Cleanup expired sessions"""
        now = datetime.now(timezone.utc)
        
        result = await self.collection.update_many(
            {
                "isActive": True,
                "expiresAt": {"$lt": now}
            },
            {"$set": {"isActive": False}}
        )
        
        if result.modified_count > 0:
            logger.info(f"Cleaned up {result.modified_count} expired sessions")
        
        return result.modified_count


async def ensure_session_indexes(db):
    """Create indexes for geo_sessions collection"""
    collection = db.geo_sessions
    
    # TTL index for automatic cleanup
    await collection.create_index("expiresAt", expireAfterSeconds=0)
    
    # Cell-based lookup
    await collection.create_index("cell")
    await collection.create_index("neighborCells")
    
    # User lookup
    await collection.create_index("userId", unique=True)
    
    # Active sessions
    await collection.create_index([("isActive", 1), ("expiresAt", 1)])
    
    logger.info("Geo session indexes created")
