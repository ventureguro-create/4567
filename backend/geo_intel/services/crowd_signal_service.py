"""
Crowd Signal Service - User-generated events
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import uuid

logger = logging.getLogger(__name__)

# Event types with TTL
EVENT_CONFIG = {
    "virus": {"ttl_hours": 2, "base_confidence": 0.35, "icon": "🦠", "label": "Вірус"},
    "trash": {"ttl_hours": 12, "base_confidence": 0.35, "icon": "🗑", "label": "Сміття"},
    "rain": {"ttl_hours": 1, "base_confidence": 0.35, "icon": "🌧", "label": "Дощ"},
    "heavy_rain": {"ttl_hours": 0.5, "base_confidence": 0.35, "icon": "⛈", "label": "Злива"},
    "blocked": {"ttl_hours": 6, "base_confidence": 0.4, "icon": "🚧", "label": "Перекриття"},
    "other": {"ttl_hours": 4, "base_confidence": 0.3, "icon": "⚠️", "label": "Інше"},
}

# Spam limits
MAX_REPORTS_PER_HOUR = 5
DEDUPE_DISTANCE_M = 100
DEDUPE_TIME_MINUTES = 15
CONFIRM_THRESHOLD = 3


class CrowdSignalService:
    """Service for user-generated geo events"""
    
    def __init__(self, db):
        self.db = db
        self.events = db.tg_geo_events
        self.confirmations = db.geo_event_confirmations
        self.user_reports = db.geo_user_reports
    
    async def can_user_report(self, actor_id: str) -> Dict[str, Any]:
        """Check if user can submit a report (spam protection)"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        
        count = await self.user_reports.count_documents({
            "actorId": actor_id,
            "createdAt": {"$gte": cutoff}
        })
        
        if count >= MAX_REPORTS_PER_HOUR:
            return {
                "allowed": False,
                "reason": f"Ліміт {MAX_REPORTS_PER_HOUR} сигналів на годину",
                "remaining": 0
            }
        
        return {
            "allowed": True,
            "remaining": MAX_REPORTS_PER_HOUR - count
        }
    
    async def find_duplicate(
        self, 
        event_type: str, 
        lat: float, 
        lng: float
    ) -> Optional[Dict[str, Any]]:
        """Find existing event to merge with"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=DEDUPE_TIME_MINUTES)
        
        # Use geospatial query
        cursor = self.events.find({
            "eventType": event_type,
            "createdAt": {"$gte": cutoff},
            "location": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "$maxDistance": DEDUPE_DISTANCE_M
                }
            }
        }).limit(1)
        
        async for doc in cursor:
            return doc
        
        return None
    
    async def create_event(
        self,
        actor_id: str,
        event_type: str,
        lat: float,
        lng: float,
        title: Optional[str] = None,
        comment: Optional[str] = None,
        photo_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create new user-generated event"""
        
        # Check spam
        spam_check = await self.can_user_report(actor_id)
        if not spam_check["allowed"]:
            return {"ok": False, "error": "SPAM_LIMIT", "message": spam_check["reason"]}
        
        # Check for duplicate
        existing = await self.find_duplicate(event_type, lat, lng)
        
        if existing:
            # Merge with existing - add confirmation
            await self.add_confirmation(
                event_id=str(existing["_id"]),
                actor_id=actor_id,
                confirmed=True
            )
            
            return {
                "ok": True,
                "action": "merged",
                "eventId": str(existing["_id"]),
                "message": "Сигнал об'єднано з існуючим"
            }
        
        # Create new event
        config = EVENT_CONFIG.get(event_type, EVENT_CONFIG["other"])
        now = datetime.now(timezone.utc)
        
        event_id = str(uuid.uuid4())[:12]
        
        doc = {
            "eventId": event_id,
            "eventType": event_type,
            "title": title or config["label"],
            "location": {
                "type": "Point",
                "coordinates": [lng, lat]
            },
            "source": "user",
            "sourceId": actor_id,
            "confidence": config["base_confidence"],
            "confirmations": 1,  # Creator counts as 1
            "confirmedBy": [actor_id],
            "status": "pending",
            "severity": 2,
            "comment": comment,
            "photoUrl": photo_url,
            "createdAt": now,
            "updatedAt": now,
            "expiresAt": now + timedelta(hours=config["ttl_hours"]),
            "dedupeKey": f"user_{event_id}",
            "actorId": actor_id,
        }
        
        await self.events.insert_one(doc)
        
        # Log user report
        await self.user_reports.insert_one({
            "actorId": actor_id,
            "eventId": event_id,
            "eventType": event_type,
            "createdAt": now
        })
        
        logger.info(f"User event created: {event_id} by {actor_id}")
        
        return {
            "ok": True,
            "action": "created",
            "eventId": event_id,
            "message": "Сигнал створено"
        }
    
    async def add_confirmation(
        self,
        event_id: str,
        actor_id: str,
        confirmed: bool
    ) -> Dict[str, Any]:
        """Add user confirmation to event"""
        
        # Find event
        event = await self.events.find_one({"eventId": event_id})
        if not event:
            # Try by _id
            from bson import ObjectId
            try:
                event = await self.events.find_one({"_id": ObjectId(event_id)})
            except:
                pass
        
        if not event:
            return {"ok": False, "error": "Event not found"}
        
        # Check if already confirmed by this user
        confirmed_by = event.get("confirmedBy", [])
        if actor_id in confirmed_by:
            return {"ok": False, "error": "Already confirmed"}
        
        # Update event
        if confirmed:
            new_confirmations = event.get("confirmations", 0) + 1
            confirmed_by.append(actor_id)
            
            # Calculate new confidence
            new_confidence = min(0.9, event.get("confidence", 0.35) + 0.15)
            
            # Update status if threshold reached
            new_status = event.get("status", "pending")
            if new_confirmations >= CONFIRM_THRESHOLD:
                new_status = "confirmed"
                new_confidence = max(new_confidence, 0.75)
            
            await self.events.update_one(
                {"_id": event["_id"]},
                {
                    "$set": {
                        "confirmations": new_confirmations,
                        "confirmedBy": confirmed_by,
                        "confidence": new_confidence,
                        "status": new_status,
                        "updatedAt": datetime.now(timezone.utc)
                    }
                }
            )
            
            # Log confirmation
            await self.confirmations.insert_one({
                "eventId": event_id,
                "actorId": actor_id,
                "confirmed": True,
                "createdAt": datetime.now(timezone.utc)
            })
            
            return {
                "ok": True,
                "confirmations": new_confirmations,
                "status": new_status,
                "confidence": new_confidence
            }
        else:
            # Negative confirmation (deny)
            await self.confirmations.insert_one({
                "eventId": event_id,
                "actorId": actor_id,
                "confirmed": False,
                "createdAt": datetime.now(timezone.utc)
            })
            
            return {"ok": True, "action": "denied"}
    
    async def get_user_stats(self, actor_id: str) -> Dict[str, Any]:
        """Get user reporting statistics"""
        total = await self.user_reports.count_documents({"actorId": actor_id})
        
        # Count confirmed reports
        confirmed = await self.events.count_documents({
            "sourceId": actor_id,
            "status": "confirmed"
        })
        
        # Calculate trust score
        trust_score = min(100, 50 + (confirmed * 10)) if total > 0 else 50
        
        return {
            "totalReports": total,
            "confirmedReports": confirmed,
            "trustScore": trust_score
        }
    
    async def get_nearby_pending(
        self,
        lat: float,
        lng: float,
        radius_m: int = 500,
        actor_id: str = None
    ) -> List[Dict[str, Any]]:
        """Get pending events nearby that user can confirm"""
        cursor = self.events.find({
            "status": "pending",
            "location": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "$maxDistance": radius_m
                }
            }
        }, {"_id": 0}).limit(5)
        
        events = []
        async for doc in cursor:
            # Skip if user already confirmed
            if actor_id and actor_id in doc.get("confirmedBy", []):
                continue
            events.append(doc)
        
        return events
