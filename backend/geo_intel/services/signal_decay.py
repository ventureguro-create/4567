"""
Signal Decay Engine
Manages event lifecycle and aging
"""
import logging
from datetime import datetime, timezone
from typing import Dict

from ..config.event_types import get_lifetime

logger = logging.getLogger(__name__)


class SignalDecayEngine:
    """Engine for computing signal decay and lifecycle"""
    
    def compute_decay(self, event: Dict) -> Dict:
        """
        Compute decay score and status for an event.
        
        Returns dict with:
        - decayScore: 0.0 - 1.0
        - ageMinutes: int
        - status: NEW/CONFIRMED/ACTIVE/DECAYING/EXPIRED
        - expiresAt: datetime
        """
        now = datetime.now(timezone.utc)
        
        last_seen = event.get("lastSeenAt")
        if last_seen is None:
            last_seen = event.get("updatedAt", now)
        
        # Handle naive datetime
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        
        age_minutes = (now - last_seen).total_seconds() / 60
        
        # Get lifetime for this event type
        event_type = event.get("eventType", "virus")
        lifetime = get_lifetime(event_type)
        
        # Calculate freshness (0.0 - 1.0)
        freshness = max(0, 1 - age_minutes / lifetime)
        
        # Get confidence
        confidence = event.get("confidence", 0.5)
        
        # Decay score = confidence * freshness
        decay_score = confidence * freshness
        
        # Determine status based on decay score
        if decay_score >= 0.75:
            status = "CONFIRMED"
        elif decay_score >= 0.45:
            status = "ACTIVE"
        elif decay_score >= 0.25:
            status = "DECAYING"
        else:
            status = "EXPIRED"
        
        return {
            "decayScore": round(decay_score, 2),
            "ageMinutes": int(age_minutes),
            "status": status,
            "freshness": round(freshness, 2),
            "expiresAt": last_seen
        }


class DecayRepository:
    """Repository for decay operations"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_active_events(self):
        """Get all non-expired fused events"""
        cursor = self.db.tg_geo_fused_events.find(
            {"status": {"$ne": "EXPIRED"}},
            {"_id": 0}
        )
        return await cursor.to_list(1000)
    
    async def update_event(self, fused_id: str, fields: Dict):
        """Update event with new decay values"""
        await self.db.tg_geo_fused_events.update_one(
            {"fusedId": fused_id},
            {"$set": fields}
        )


class DecayWorker:
    """Background worker for signal decay"""
    
    def __init__(self, db):
        self.db = db
        self.running = False
    
    async def run_once(self) -> Dict:
        """Run single decay cycle"""
        repo = DecayRepository(self.db)
        engine = SignalDecayEngine()
        
        events = await repo.get_active_events()
        updated = 0
        expired = 0
        
        for event in events:
            result = engine.compute_decay(event)
            
            # Only update if status changed or significant decay
            old_status = event.get("status")
            old_decay = event.get("decayScore", 1.0)
            
            if result["status"] != old_status or abs(result["decayScore"] - old_decay) > 0.1:
                await repo.update_event(event["fusedId"], result)
                updated += 1
                
                if result["status"] == "EXPIRED":
                    expired += 1
        
        return {"ok": True, "updated": updated, "expired": expired}
