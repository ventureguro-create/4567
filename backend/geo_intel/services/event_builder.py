"""
Event Builder Engine - Signal Intelligence v2.0

This module implements the advanced event correlation system:

Pipeline:
    Telegram Parser → Slang Normalizer → Keyword Filter → AI Classifier 
    → Location Extractor → Geocoder → Signal Engine → EVENT BUILDER → Map/Alerts

Key Features:
1. Dedup Engine - объединение сигналов в радиусе 300м и времени 20 мин
2. Event Confidence - формула с reports, sources, trust, decay
3. Signal Decay - TTL продлевается при новых репортах  
4. Negative Filter - обработка "чисто/вільно/пусто" сообщений
5. Multi-source Correlation - разные источники = выше confidence
6. Event Status Lifecycle - candidate → correlated → verified → expired

Tables:
- geo_events: подтверждённые объединённые события
- geo_signal_reports: связь сигналов с событиями

Author: Signal Intelligence System
"""
import logging
import uuid
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from ..utils.geo_distance import haversine_distance

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Dedup/Correlation parameters
DEDUP_DISTANCE_M = 300  # meters - signals within this radius are merged
DEDUP_TIME_WINDOW_MIN = 20  # minutes - time window for correlation
CONFIDENCE_THRESHOLD = 0.65  # minimum confidence for verified status

# Signal type priorities
SIGNAL_PRIORITY = {
    "detention": 0.90,
    "raid": 0.85,
    "checkpoint": 0.80,
    "police": 0.75,
    "danger": 0.80,
    "fire": 0.90,
    "accident": 0.75,
    "virus": 0.70,
    "weather": 0.50,
    "rain": 0.50,
    "heavy_rain": 0.60,
    "trash": 0.40,
    "flood": 0.70,
    "incident": 0.75,
}

# Default TTL per signal type (minutes)
DEFAULT_TTL = {
    "detention": 120,
    "raid": 90,
    "checkpoint": 60,
    "police": 45,
    "danger": 60,
    "fire": 90,
    "accident": 60,
    "virus": 120,
    "weather": 180,
    "rain": 120,
    "heavy_rain": 90,
    "trash": 480,
    "flood": 240,
    "incident": 60,
}

# Negative keywords dictionary (Ukrainian, Russian, English)
NEGATIVE_KEYWORDS = [
    # Ukrainian
    "чисто", "вільно", "пусто", "розійшлись", "немає", "нема", "проїхали",
    "зняли", "забрали", "поїхали", "закінчилось", "все ок", "все гаразд",
    # Russian
    "чисто", "свободно", "пусто", "разошлись", "нету", "нет", "уехали",
    "сняли", "убрали", "закончилось", "всё ок", "всё хорошо",
    # English
    "clear", "empty", "gone", "left", "removed", "finished", "all good",
]

# Source weights for confidence calculation
SOURCE_WEIGHTS = {
    "trusted_channel": 0.80,
    "new_channel": 0.50,
    "user_report": 0.60,
    "user_report_photo": 0.80,
    "admin_signal": 1.00,
}

# =============================================================================
# EVENT STATUS ENUM
# =============================================================================

class EventStatus:
    CANDIDATE = "candidate"     # 1 сигнал
    CORRELATED = "correlated"   # 2 сигнала
    VERIFIED = "verified"       # 2+ источника и confidence > 0.75
    EXPIRED = "expired"         # TTL закончился
    DISMISSED = "dismissed"     # отклонено модерацией или негативными репортами


class EventStrength:
    WEAK = "weak"       # 1 источник
    MEDIUM = "medium"   # 2 сигнала / 1-2 источника
    STRONG = "strong"   # 3+ источника
    CRITICAL = "critical"  # detention/raid + user confirmation + photo


# =============================================================================
# CONFIDENCE CALCULATOR
# =============================================================================

class ConfidenceCalculator:
    """
    Advanced confidence calculation using formula:
    
    event_confidence = 
        ai_confidence_avg * 0.30
        + source_count_weight * 0.25  
        + source_diversity_weight * 0.20
        + recency_weight * 0.15
        + user_confirmation_weight * 0.10
    """
    
    @staticmethod
    def calculate(
        ai_confidence: float = 0.5,
        report_count: int = 1,
        unique_sources: int = 1,
        age_minutes: float = 0,
        user_confirmations: int = 0,
        has_photo: bool = False,
        signal_type: str = "virus",
        is_location_known: bool = True,
    ) -> Dict[str, float]:
        """
        Calculate event confidence with detailed breakdown.
        
        Returns:
            {
                "confidence": float,
                "breakdown": {
                    "ai": float,
                    "reports": float,
                    "sources": float,
                    "recency": float,
                    "confirmations": float
                },
                "bonuses": float,
                "penalties": float
            }
        """
        # Base weights
        ai_weight = 0.30
        reports_weight = 0.25
        sources_weight = 0.20
        recency_weight = 0.15
        confirm_weight = 0.10
        
        # 1. AI confidence component (0-1)
        ai_component = min(1.0, ai_confidence) * ai_weight
        
        # 2. Reports count component (logarithmic scale)
        # 1 report = 0.2, 2 = 0.4, 3 = 0.6, 5+ = 0.8+
        reports_score = min(1.0, math.log2(report_count + 1) / 3)
        reports_component = reports_score * reports_weight
        
        # 3. Source diversity component
        # 1 source = 0.3, 2 = 0.6, 3+ = 1.0
        sources_score = min(1.0, unique_sources / 3)
        sources_component = sources_score * sources_weight
        
        # 4. Recency component (decay over time)
        # Fresh (0-5min) = 1.0, 20min = 0.5, 60min = 0.1
        ttl = DEFAULT_TTL.get(signal_type, 60)
        recency_score = max(0, 1 - (age_minutes / ttl))
        recency_component = recency_score * recency_weight
        
        # 5. User confirmations component
        # 0 = 0, 1 = 0.3, 2 = 0.6, 3+ = 1.0  
        confirm_score = min(1.0, user_confirmations / 3)
        confirm_component = confirm_score * confirm_weight
        
        # Base confidence
        base_confidence = (
            ai_component + 
            reports_component + 
            sources_component + 
            recency_component + 
            confirm_component
        )
        
        # Bonuses
        bonuses = 0
        if has_photo:
            bonuses += 0.15  # Photo bonus
        if unique_sources > 2:
            bonuses += 0.05  # Multi-source bonus
        
        # Penalties
        penalties = 0
        if not is_location_known:
            penalties += 0.20  # Unknown location penalty
        
        # Type priority adjustment
        type_priority = SIGNAL_PRIORITY.get(signal_type, 0.5)
        
        # Final confidence
        final_confidence = min(1.0, max(0, (base_confidence + bonuses - penalties) * type_priority + (1 - type_priority) * base_confidence))
        
        return {
            "confidence": round(final_confidence, 3),
            "breakdown": {
                "ai": round(ai_component, 3),
                "reports": round(reports_component, 3),
                "sources": round(sources_component, 3),
                "recency": round(recency_component, 3),
                "confirmations": round(confirm_component, 3),
            },
            "bonuses": round(bonuses, 3),
            "penalties": round(penalties, 3),
            "type_priority": type_priority,
        }


# =============================================================================
# DEDUP ENGINE
# =============================================================================

class DedupEngine:
    """
    Deduplication engine for merging similar signals.
    
    Logic:
        If distance < 300m AND type is same AND time < 20 min:
            → это один сигнал
    """
    
    @staticmethod
    def find_matching_event(
        events: List[Dict],
        signal_type: str,
        lat: float,
        lng: float,
        created_at: datetime,
    ) -> Optional[Dict]:
        """
        Find existing event that matches the new signal.
        
        Returns matching event or None.
        """
        for event in events:
            # Check type match
            if event.get("type") != signal_type:
                continue
            
            # Check distance
            event_lat = event.get("lat")
            event_lng = event.get("lng")
            if event_lat is None or event_lng is None:
                continue
                
            distance = haversine_distance(lat, lng, event_lat, event_lng)
            if distance > DEDUP_DISTANCE_M:
                continue
            
            # Check time window
            event_updated = event.get("updated_at") or event.get("created_at")
            if event_updated:
                if isinstance(event_updated, str):
                    event_updated = datetime.fromisoformat(event_updated.replace('Z', '+00:00'))
                if event_updated.tzinfo is None:
                    event_updated = event_updated.replace(tzinfo=timezone.utc)
                
                time_diff = abs((created_at - event_updated).total_seconds() / 60)
                if time_diff > DEDUP_TIME_WINDOW_MIN:
                    continue
            
            return event
        
        return None
    
    @staticmethod
    def is_duplicate(
        signal_type: str,
        lat: float,
        lng: float,
        created_at: datetime,
        existing_event: Dict,
    ) -> bool:
        """Check if signal is duplicate of existing event."""
        if existing_event.get("type") != signal_type:
            return False
        
        event_lat = existing_event.get("lat")
        event_lng = existing_event.get("lng")
        if event_lat is None or event_lng is None:
            return False
        
        distance = haversine_distance(lat, lng, event_lat, event_lng)
        if distance > DEDUP_DISTANCE_M:
            return False
        
        event_updated = existing_event.get("updated_at") or existing_event.get("created_at")
        if event_updated:
            if isinstance(event_updated, str):
                event_updated = datetime.fromisoformat(event_updated.replace('Z', '+00:00'))
            if event_updated.tzinfo is None:
                event_updated = event_updated.replace(tzinfo=timezone.utc)
            
            time_diff = abs((created_at - event_updated).total_seconds() / 60)
            if time_diff > DEDUP_TIME_WINDOW_MIN:
                return False
        
        return True


# =============================================================================
# NEGATIVE FILTER
# =============================================================================

class NegativeFilter:
    """
    Filter for negative/clearing messages.
    
    If message contains "чисто", "вільно", "пусто" etc:
        → event confidence drops
        → or event gets expired
    """
    
    @staticmethod
    def is_negative(text: str) -> bool:
        """Check if text contains negative keywords."""
        if not text:
            return False
        
        text_lower = text.lower()
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
    
    @staticmethod
    def get_confidence_penalty(text: str) -> float:
        """
        Get confidence penalty based on negative keywords.
        
        Returns penalty value (0 - 0.5)
        """
        if not text:
            return 0
        
        text_lower = text.lower()
        penalty = 0
        
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in text_lower:
                penalty += 0.15
        
        return min(0.5, penalty)  # Max 50% penalty


# =============================================================================
# EVENT BUILDER
# =============================================================================

class EventBuilder:
    """
    Main Event Builder Engine.
    
    Pipeline:
        Signal → Find matching event → Merge or Create new → Update confidence
    """
    
    def __init__(self, db):
        self.db = db
        self.dedup = DedupEngine()
        self.negative_filter = NegativeFilter()
        self.confidence_calc = ConfidenceCalculator()
    
    async def process_signal(
        self,
        signal_type: str,
        lat: float,
        lng: float,
        source: str,
        source_channel: str = None,
        text: str = None,
        ai_confidence: float = 0.5,
        has_photo: bool = False,
        user_id: str = None,
        message_id: str = None,
    ) -> Dict[str, Any]:
        """
        Process incoming signal and create/update event.
        
        Steps:
        1. Check for negative message
        2. Find matching existing event
        3. If found: merge (increment reports, recalc confidence, extend TTL)
        4. If not found: create new event with status=candidate
        
        Returns:
            {
                "action": "created" | "merged" | "expired",
                "event_id": str,
                "event": dict,
                "is_negative": bool
            }
        """
        now = datetime.now(timezone.utc)
        
        # Step 1: Check negative message
        is_negative = self.negative_filter.is_negative(text) if text else False
        
        if is_negative:
            # Find and expire matching event
            return await self._handle_negative_signal(signal_type, lat, lng, text, now)
        
        # Step 2: Get active events of same type
        active_events = await self._get_active_events(signal_type)
        
        # Step 3: Find matching event
        matching_event = self.dedup.find_matching_event(
            events=active_events,
            signal_type=signal_type,
            lat=lat,
            lng=lng,
            created_at=now,
        )
        
        if matching_event:
            # Step 4a: Merge with existing event
            return await self._merge_signal(
                event=matching_event,
                source=source,
                source_channel=source_channel,
                text=text,
                ai_confidence=ai_confidence,
                has_photo=has_photo,
                user_id=user_id,
                message_id=message_id,
                now=now,
            )
        else:
            # Step 4b: Create new event
            return await self._create_event(
                signal_type=signal_type,
                lat=lat,
                lng=lng,
                source=source,
                source_channel=source_channel,
                text=text,
                ai_confidence=ai_confidence,
                has_photo=has_photo,
                user_id=user_id,
                message_id=message_id,
                now=now,
            )
    
    async def _get_active_events(self, signal_type: str = None) -> List[Dict]:
        """Get active (non-expired) events."""
        now = datetime.now(timezone.utc)
        
        query = {
            "status": {"$nin": [EventStatus.EXPIRED, EventStatus.DISMISSED]},
            "expires_at": {"$gt": now},
        }
        
        if signal_type:
            query["type"] = signal_type
        
        events = await self.db.geo_events.find(
            query,
            {"_id": 0}
        ).to_list(500)
        
        return events
    
    async def _handle_negative_signal(
        self,
        signal_type: str,
        lat: float,
        lng: float,
        text: str,
        now: datetime,
    ) -> Dict[str, Any]:
        """Handle negative/clearing signal."""
        # Find matching event to expire
        active_events = await self._get_active_events(signal_type)
        
        matching_event = self.dedup.find_matching_event(
            events=active_events,
            signal_type=signal_type,
            lat=lat,
            lng=lng,
            created_at=now,
        )
        
        if matching_event:
            event_id = matching_event.get("event_id")
            
            # Reduce confidence or expire
            old_confidence = matching_event.get("confidence", 0.5)
            penalty = self.negative_filter.get_confidence_penalty(text)
            new_confidence = max(0, old_confidence - penalty)
            
            # Increment negative reports
            negative_count = matching_event.get("negative_reports", 0) + 1
            
            # Expire if confidence too low or many negative reports
            if new_confidence < 0.3 or negative_count >= 3:
                await self.db.geo_events.update_one(
                    {"event_id": event_id},
                    {"$set": {
                        "status": EventStatus.EXPIRED,
                        "expired_reason": "negative_reports",
                        "negative_reports": negative_count,
                        "confidence": new_confidence,
                        "updated_at": now,
                    }}
                )
                action = "expired"
            else:
                await self.db.geo_events.update_one(
                    {"event_id": event_id},
                    {"$set": {
                        "confidence": new_confidence,
                        "negative_reports": negative_count,
                        "updated_at": now,
                    }}
                )
                action = "reduced_confidence"
            
            return {
                "action": action,
                "event_id": event_id,
                "event": matching_event,
                "is_negative": True,
                "confidence_change": round(old_confidence - new_confidence, 2),
            }
        
        return {
            "action": "ignored",
            "event_id": None,
            "event": None,
            "is_negative": True,
            "message": "No matching event to expire",
        }
    
    async def _merge_signal(
        self,
        event: Dict,
        source: str,
        source_channel: str,
        text: str,
        ai_confidence: float,
        has_photo: bool,
        user_id: str,
        message_id: str,
        now: datetime,
    ) -> Dict[str, Any]:
        """Merge signal into existing event."""
        event_id = event.get("event_id")
        
        # Get current values
        old_report_count = event.get("report_count", 1)
        old_sources = set(event.get("unique_sources", []))
        old_confirmations = event.get("user_confirmations", 0)
        old_photos = event.get("photo_count", 0)
        
        # Update values
        new_report_count = old_report_count + 1
        
        # Add source if new
        if source_channel and source_channel not in old_sources:
            old_sources.add(source_channel)
        if user_id and user_id not in old_sources:
            old_sources.add(user_id)
        
        new_unique_sources = list(old_sources)
        
        # Photo count
        new_photo_count = old_photos + (1 if has_photo else 0)
        
        # Calculate age
        created_at = event.get("created_at", now)
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age_minutes = (now - created_at).total_seconds() / 60
        
        # Recalculate confidence
        confidence_result = self.confidence_calc.calculate(
            ai_confidence=ai_confidence,
            report_count=new_report_count,
            unique_sources=len(new_unique_sources),
            age_minutes=age_minutes,
            user_confirmations=old_confirmations,
            has_photo=(new_photo_count > 0),
            signal_type=event.get("type", "virus"),
            is_location_known=True,
        )
        
        new_confidence = confidence_result["confidence"]
        
        # Determine new status
        new_status = self._determine_status(
            report_count=new_report_count,
            unique_sources=len(new_unique_sources),
            confidence=new_confidence,
        )
        
        # Determine strength
        new_strength = self._determine_strength(
            unique_sources=len(new_unique_sources),
            has_photo=(new_photo_count > 0),
            signal_type=event.get("type"),
            user_confirmations=old_confirmations,
        )
        
        # Extend TTL (add 10 minutes per new report)
        old_expires = event.get("expires_at", now + timedelta(minutes=60))
        if isinstance(old_expires, str):
            old_expires = datetime.fromisoformat(old_expires.replace('Z', '+00:00'))
        if old_expires.tzinfo is None:
            old_expires = old_expires.replace(tzinfo=timezone.utc)
        new_expires = old_expires + timedelta(minutes=10)
        
        # Update event
        await self.db.geo_events.update_one(
            {"event_id": event_id},
            {"$set": {
                "report_count": new_report_count,
                "unique_sources": new_unique_sources,
                "source_count": len(new_unique_sources),
                "photo_count": new_photo_count,
                "confidence": new_confidence,
                "confidence_breakdown": confidence_result["breakdown"],
                "status": new_status,
                "strength": new_strength,
                "expires_at": new_expires,
                "updated_at": now,
                "last_report_at": now,
            }}
        )
        
        # Save signal report link
        await self._save_signal_report(
            event_id=event_id,
            source=source,
            source_channel=source_channel,
            text=text,
            user_id=user_id,
            message_id=message_id,
            ai_confidence=ai_confidence,
            has_photo=has_photo,
            now=now,
        )
        
        # Get updated event
        updated_event = await self.db.geo_events.find_one(
            {"event_id": event_id},
            {"_id": 0}
        )
        
        return {
            "action": "merged",
            "event_id": event_id,
            "event": updated_event,
            "is_negative": False,
            "new_report_count": new_report_count,
            "new_confidence": new_confidence,
            "status_change": event.get("status") != new_status,
        }
    
    async def _create_event(
        self,
        signal_type: str,
        lat: float,
        lng: float,
        source: str,
        source_channel: str,
        text: str,
        ai_confidence: float,
        has_photo: bool,
        user_id: str,
        message_id: str,
        now: datetime,
    ) -> Dict[str, Any]:
        """Create new event from signal."""
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        
        # Calculate initial confidence
        unique_sources = []
        if source_channel:
            unique_sources.append(source_channel)
        if user_id:
            unique_sources.append(user_id)
        
        confidence_result = self.confidence_calc.calculate(
            ai_confidence=ai_confidence,
            report_count=1,
            unique_sources=len(unique_sources) or 1,
            age_minutes=0,
            user_confirmations=0,
            has_photo=has_photo,
            signal_type=signal_type,
            is_location_known=True,
        )
        
        confidence = confidence_result["confidence"]
        
        # Initial TTL
        ttl_minutes = DEFAULT_TTL.get(signal_type, 60)
        expires_at = now + timedelta(minutes=ttl_minutes)
        
        # Create event document
        event_doc = {
            "event_id": event_id,
            "type": signal_type,
            "lat": lat,
            "lng": lng,
            "location": {
                "type": "Point",
                "coordinates": [lng, lat]
            },
            "report_count": 1,
            "unique_sources": unique_sources or [source],
            "source_count": len(unique_sources) or 1,
            "photo_count": 1 if has_photo else 0,
            "user_confirmations": 0,
            "negative_reports": 0,
            "confidence": confidence,
            "confidence_breakdown": confidence_result["breakdown"],
            "status": EventStatus.CANDIDATE,
            "strength": EventStrength.WEAK,
            "created_at": now,
            "updated_at": now,
            "last_report_at": now,
            "expires_at": expires_at,
            "ttl_minutes": ttl_minutes,
        }
        
        await self.db.geo_events.insert_one(event_doc)
        
        # Save signal report link
        await self._save_signal_report(
            event_id=event_id,
            source=source,
            source_channel=source_channel,
            text=text,
            user_id=user_id,
            message_id=message_id,
            ai_confidence=ai_confidence,
            has_photo=has_photo,
            now=now,
        )
        
        # Remove _id for response
        event_doc.pop("_id", None)
        
        return {
            "action": "created",
            "event_id": event_id,
            "event": event_doc,
            "is_negative": False,
        }
    
    async def _save_signal_report(
        self,
        event_id: str,
        source: str,
        source_channel: str,
        text: str,
        user_id: str,
        message_id: str,
        ai_confidence: float,
        has_photo: bool,
        now: datetime,
    ):
        """Save signal report to geo_signal_reports collection."""
        report_doc = {
            "report_id": f"rpt_{uuid.uuid4().hex[:12]}",
            "event_id": event_id,
            "source": source,
            "source_channel": source_channel,
            "original_text": text,
            "user_id": user_id,
            "message_id": message_id,
            "ai_confidence": ai_confidence,
            "has_photo": has_photo,
            "created_at": now,
        }
        
        await self.db.geo_signal_reports.insert_one(report_doc)
    
    def _determine_status(
        self,
        report_count: int,
        unique_sources: int,
        confidence: float,
    ) -> str:
        """Determine event status based on reports and confidence."""
        if confidence >= CONFIDENCE_THRESHOLD and unique_sources >= 2:
            return EventStatus.VERIFIED
        elif report_count >= 2:
            return EventStatus.CORRELATED
        else:
            return EventStatus.CANDIDATE
    
    def _determine_strength(
        self,
        unique_sources: int,
        has_photo: bool,
        signal_type: str,
        user_confirmations: int,
    ) -> str:
        """Determine event strength."""
        high_priority_types = ["detention", "raid", "fire", "danger"]
        
        if signal_type in high_priority_types and user_confirmations > 0 and has_photo:
            return EventStrength.CRITICAL
        elif unique_sources >= 3:
            return EventStrength.STRONG
        elif unique_sources >= 2 or (unique_sources == 1 and has_photo):
            return EventStrength.MEDIUM
        else:
            return EventStrength.WEAK
    
    async def confirm_event(
        self,
        event_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """User confirms event (they see it too)."""
        now = datetime.now(timezone.utc)
        
        event = await self.db.geo_events.find_one({"event_id": event_id})
        if not event:
            return {"ok": False, "error": "Event not found"}
        
        # Check if user already confirmed
        confirmed_by = event.get("confirmed_by", [])
        if user_id in confirmed_by:
            return {"ok": False, "error": "Already confirmed"}
        
        # Update confirmations
        new_confirmations = event.get("user_confirmations", 0) + 1
        confirmed_by.append(user_id)
        
        # Recalculate confidence
        confidence_result = self.confidence_calc.calculate(
            ai_confidence=event.get("confidence", 0.5),
            report_count=event.get("report_count", 1),
            unique_sources=event.get("source_count", 1),
            age_minutes=0,  # Fresh confirmation
            user_confirmations=new_confirmations,
            has_photo=event.get("photo_count", 0) > 0,
            signal_type=event.get("type", "virus"),
        )
        
        new_confidence = confidence_result["confidence"]
        
        # Determine new status
        new_status = self._determine_status(
            report_count=event.get("report_count", 1),
            unique_sources=event.get("source_count", 1),
            confidence=new_confidence,
        )
        
        # Extend TTL by 10 minutes
        old_expires = event.get("expires_at", now)
        if isinstance(old_expires, str):
            old_expires = datetime.fromisoformat(old_expires.replace('Z', '+00:00'))
        if old_expires.tzinfo is None:
            old_expires = old_expires.replace(tzinfo=timezone.utc)
        new_expires = old_expires + timedelta(minutes=10)
        
        await self.db.geo_events.update_one(
            {"event_id": event_id},
            {"$set": {
                "user_confirmations": new_confirmations,
                "confirmed_by": confirmed_by,
                "confidence": new_confidence,
                "status": new_status,
                "expires_at": new_expires,
                "updated_at": now,
            }}
        )
        
        return {
            "ok": True,
            "event_id": event_id,
            "new_confirmations": new_confirmations,
            "new_confidence": new_confidence,
            "new_status": new_status,
        }
    
    async def report_not_there(
        self,
        event_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """User reports event is not there anymore."""
        now = datetime.now(timezone.utc)
        
        event = await self.db.geo_events.find_one({"event_id": event_id})
        if not event:
            return {"ok": False, "error": "Event not found"}
        
        # Increment negative reports
        negative_count = event.get("negative_reports", 0) + 1
        
        # Reduce confidence
        old_confidence = event.get("confidence", 0.5)
        new_confidence = max(0, old_confidence - 0.15)
        
        # Expire if too many negative reports
        if negative_count >= 3 or new_confidence < 0.3:
            await self.db.geo_events.update_one(
                {"event_id": event_id},
                {"$set": {
                    "status": EventStatus.EXPIRED,
                    "expired_reason": "user_not_there",
                    "negative_reports": negative_count,
                    "confidence": new_confidence,
                    "updated_at": now,
                }}
            )
            return {
                "ok": True,
                "event_id": event_id,
                "action": "expired",
                "negative_reports": negative_count,
            }
        
        await self.db.geo_events.update_one(
            {"event_id": event_id},
            {"$set": {
                "negative_reports": negative_count,
                "confidence": new_confidence,
                "updated_at": now,
            }}
        )
        
        return {
            "ok": True,
            "event_id": event_id,
            "action": "reduced",
            "new_confidence": new_confidence,
            "negative_reports": negative_count,
        }
    
    async def get_map_events(
        self,
        days: int = 7,
        limit: int = 100,
        event_type: str = None,
    ) -> List[Dict]:
        """Get events for map display (events, not raw signals)."""
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        
        query = {
            "status": {"$nin": [EventStatus.EXPIRED, EventStatus.DISMISSED]},
            "created_at": {"$gte": since},
        }
        
        if event_type:
            query["type"] = event_type
        
        events = await self.db.geo_events.find(
            query,
            {"_id": 0}
        ).sort("updated_at", -1).limit(limit).to_list(limit)
        
        return events
    
    async def get_event_reports(self, event_id: str) -> List[Dict]:
        """Get all signal reports for an event."""
        reports = await self.db.geo_signal_reports.find(
            {"event_id": event_id},
            {"_id": 0}
        ).sort("created_at", -1).to_list(50)
        
        return reports


# =============================================================================
# INDEX CREATION
# =============================================================================

async def ensure_event_builder_indexes(db):
    """Create indexes for event builder collections."""
    # geo_events indexes
    await db.geo_events.create_index("event_id", unique=True)
    await db.geo_events.create_index("type")
    await db.geo_events.create_index("status")
    await db.geo_events.create_index("created_at")
    await db.geo_events.create_index("updated_at")
    await db.geo_events.create_index("expires_at")
    await db.geo_events.create_index([("location", "2dsphere")])
    
    # Compound index for dedup queries
    await db.geo_events.create_index([
        ("type", 1),
        ("status", 1),
        ("expires_at", 1),
    ])
    
    # geo_signal_reports indexes
    await db.geo_signal_reports.create_index("report_id", unique=True)
    await db.geo_signal_reports.create_index("event_id")
    await db.geo_signal_reports.create_index("source_channel")
    await db.geo_signal_reports.create_index("created_at")
    
    logger.info("Event Builder indexes created")
