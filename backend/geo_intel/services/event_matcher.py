"""
Event Matcher Service
Cell-based event matching for fast alert delivery
Two-stage matching: coarse (cell) -> exact (distance)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from .cell_encoder import get_cells_for_radius, haversine_distance

logger = logging.getLogger(__name__)


class EventMatcherService:
    """
    Matches events to user sessions using cell-based lookup
    Much faster than calculating distance for every user
    """
    
    def __init__(self, db):
        self.db = db
        self.sessions_collection = db.geo_sessions
        self.cooldown_collection = db.geo_alert_cooldowns
    
    async def find_users_for_event(
        self,
        event_lat: float,
        event_lng: float,
        event_type: str,
        event_id: str,
        max_radius: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        Find all users who should receive alert for this event
        
        Two-stage matching:
        1. Coarse filter: Find sessions in nearby cells
        2. Exact filter: Calculate actual distance
        
        Args:
            event_lat, event_lng: Event location
            event_type: Type of event (virus, trash, etc.)
            event_id: Event ID for deduplication
            max_radius: Maximum search radius
        
        Returns:
            List of matching sessions with distance
        """
        now = datetime.now(timezone.utc)
        
        # Get cells for the event location
        cell_data = get_cells_for_radius(event_lat, event_lng, max_radius)
        event_cells = cell_data["neighbors"]
        
        # Stage 1: Coarse filter - find candidate sessions by cell
        candidates = await self.sessions_collection.find(
            {
                "isActive": True,
                "expiresAt": {"$gt": now},
                "$or": [
                    {"cell": {"$in": event_cells}},
                    {"neighborCells": {"$elemMatch": {"$in": event_cells}}}
                ]
            },
            {"_id": 0}
        ).to_list(1000)
        
        logger.debug(f"Stage 1: Found {len(candidates)} candidate sessions")
        
        # Stage 2: Exact filter - calculate actual distance
        matches = []
        
        for session in candidates:
            user_lat = session.get("originalLat") or session.get("lat")
            user_lng = session.get("originalLng") or session.get("lng")
            user_radius = session.get("radius", 1000)
            
            # Calculate actual distance
            distance = haversine_distance(
                event_lat, event_lng,
                user_lat, user_lng
            )
            
            # Check if within user's radius
            if distance <= user_radius:
                # Check cooldown
                is_cooled = await self._check_cooldown(
                    session["userId"],
                    event_type,
                    session.get("cell")
                )
                
                if not is_cooled:
                    matches.append({
                        **session,
                        "distance": round(distance),
                        "eventType": event_type,
                        "eventId": event_id
                    })
        
        logger.info(f"Event {event_id}: {len(candidates)} candidates -> {len(matches)} matches")
        
        return matches
    
    async def _check_cooldown(
        self,
        user_id: str,
        event_type: str,
        cell: str,
        cooldown_minutes: int = 20
    ) -> bool:
        """
        Check if user is in cooldown for this type+cell
        Prevents spam for similar events in same area
        
        Returns:
            True if in cooldown (should NOT send), False if can send
        """
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=cooldown_minutes)
        
        # Check existing cooldown
        existing = await self.cooldown_collection.find_one({
            "userId": user_id,
            "eventType": event_type,
            "cell": cell,
            "sentAt": {"$gt": threshold}
        })
        
        return existing is not None
    
    async def set_cooldown(
        self,
        user_id: str,
        event_type: str,
        cell: str,
        event_id: str
    ) -> None:
        """Record that alert was sent (for cooldown tracking)"""
        now = datetime.now(timezone.utc)
        
        await self.cooldown_collection.update_one(
            {
                "userId": user_id,
                "eventType": event_type,
                "cell": cell
            },
            {
                "$set": {
                    "sentAt": now,
                    "lastEventId": event_id
                }
            },
            upsert=True
        )
    
    async def get_nearby_events(
        self,
        user_id: str,
        lat: float,
        lng: float,
        radius: int = 1000,
        hours: int = 24,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get events near a location (for "What's nearby" feature)
        Uses cell-based lookup for speed
        """
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=hours)
        
        cell_data = get_cells_for_radius(lat, lng, radius)
        cells = cell_data["neighbors"]
        
        # Find events in cells
        events = await self.db.tg_geo_events.find(
            {
                "cell": {"$in": cells},
                "createdAt": {"$gt": cutoff},
                "isActive": {"$ne": False}
            },
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit * 2).to_list(limit * 2)
        
        # Filter by exact distance and sort
        nearby = []
        for event in events:
            event_lat = event.get("lat")
            event_lng = event.get("lng")
            
            if event_lat and event_lng:
                distance = haversine_distance(lat, lng, event_lat, event_lng)
                if distance <= radius:
                    event["distance"] = round(distance)
                    nearby.append(event)
        
        # Sort by distance and limit
        nearby.sort(key=lambda x: x.get("distance", 9999))
        
        return nearby[:limit]


class AlertBatcherService:
    """
    Batches multiple events into single alerts
    Reduces notification spam
    """
    
    def __init__(self, db):
        self.db = db
        self.batch_collection = db.geo_alert_batches
    
    async def add_to_batch(
        self,
        user_id: str,
        event: Dict[str, Any],
        batch_window_seconds: int = 60
    ) -> Optional[Dict[str, Any]]:
        """
        Add event to user's batch
        Returns batch if ready to send (window expired)
        """
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=batch_window_seconds)
        
        # Try to add to existing batch
        result = await self.batch_collection.find_one_and_update(
            {
                "userId": user_id,
                "createdAt": {"$gt": window_start},
                "sent": False
            },
            {
                "$push": {"events": event},
                "$set": {"updatedAt": now}
            },
            return_document=True
        )
        
        if result:
            return None  # Added to existing batch, not ready yet
        
        # Create new batch
        batch = {
            "userId": user_id,
            "events": [event],
            "createdAt": now,
            "updatedAt": now,
            "sent": False
        }
        
        await self.batch_collection.insert_one(batch)
        return None  # New batch created, not ready yet
    
    async def get_ready_batches(self, min_age_seconds: int = 60) -> List[Dict[str, Any]]:
        """Get batches ready to send"""
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(seconds=min_age_seconds)
        
        batches = await self.batch_collection.find(
            {
                "sent": False,
                "createdAt": {"$lt": threshold}
            },
            {"_id": 0}
        ).to_list(100)
        
        return batches
    
    async def mark_batch_sent(self, user_id: str, batch_id: str = None) -> None:
        """Mark batch as sent"""
        query = {"userId": user_id, "sent": False}
        
        await self.batch_collection.update_many(
            query,
            {"$set": {"sent": True, "sentAt": datetime.now(timezone.utc)}}
        )


async def ensure_matcher_indexes(db):
    """Create indexes for event matcher collections"""
    # Cooldown indexes
    await db.geo_alert_cooldowns.create_index(
        [("userId", 1), ("eventType", 1), ("cell", 1)],
        unique=True
    )
    await db.geo_alert_cooldowns.create_index("sentAt")
    
    # TTL for cooldowns (auto-cleanup after 1 hour)
    await db.geo_alert_cooldowns.create_index(
        "sentAt",
        expireAfterSeconds=3600
    )
    
    # Batch indexes
    await db.geo_alert_batches.create_index([("userId", 1), ("sent", 1)])
    await db.geo_alert_batches.create_index("createdAt")
    
    # TTL for batches (auto-cleanup after 1 day)
    await db.geo_alert_batches.create_index(
        "createdAt",
        expireAfterSeconds=86400
    )
    
    logger.info("Event matcher indexes created")
