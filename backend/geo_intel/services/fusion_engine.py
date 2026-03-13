"""
Event Fusion Engine
Combines multiple raw events into single fused events
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List

from ..utils.geo_distance import haversine_distance
from ..config.event_types import get_severity
from .fusion_repository import FusionRepository
from .fusion_scoring import compute_fusion_confidence, compute_status

logger = logging.getLogger(__name__)

# Fusion parameters
DISTANCE_THRESHOLD = 80  # meters
TIME_WINDOW = 20  # minutes


class FusionEngine:
    """Engine for combining raw events into fused events"""
    
    def __init__(self, repo: FusionRepository):
        self.repo = repo
    
    def _make_fused_id(self, event_type: str, lat: float, lng: float) -> str:
        """Create unique ID for fused event"""
        lat_key = round(lat, 3)
        lng_key = round(lng, 3)
        return f"{event_type}_{lat_key}_{lng_key}"
    
    async def rebuild(self) -> Dict:
        """Rebuild fused events from recent raw events"""
        raw_events = await self.repo.get_recent_raw_events(minutes=60)
        
        if not raw_events:
            logger.debug("No raw events for fusion")
            return {"ok": True, "fused": 0}
        
        # Cluster events
        clusters = []
        
        for event in raw_events:
            loc = event.get("location", {})
            elat = loc.get("lat")
            elng = loc.get("lng")
            etype = event.get("eventType", "virus")
            created = event.get("createdAt")
            
            if elat is None or elng is None or created is None:
                continue
            
            # Handle naive datetime
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            
            matched = False
            
            for cluster in clusters:
                # Check if same type
                if cluster["eventType"] != etype:
                    continue
                
                # Check distance
                dist = haversine_distance(elat, elng, cluster["lat"], cluster["lng"])
                if dist > DISTANCE_THRESHOLD:
                    continue
                
                # Check time window
                time_diff = abs((created - cluster["lastSeenAt"]).total_seconds()) / 60
                if time_diff > TIME_WINDOW:
                    continue
                
                # Add to cluster
                cluster["events"].append(event)
                cluster["lastSeenAt"] = max(cluster["lastSeenAt"], created)
                matched = True
                break
            
            if not matched:
                # Create new cluster
                clusters.append({
                    "eventType": etype,
                    "lat": elat,
                    "lng": elng,
                    "title": event.get("title", etype),
                    "firstSeenAt": created,
                    "lastSeenAt": created,
                    "events": [event]
                })
        
        # Process clusters into fused events
        fused_count = 0
        now = datetime.now(timezone.utc)
        
        for cluster in clusters:
            source_count = len(cluster["events"])
            
            # Get unique channels
            source_channels = list(set(
                e.get("source", {}).get("username", "unknown")
                for e in cluster["events"]
            ))
            channel_count = len(source_channels)
            
            # Calculate freshness
            freshness_minutes = (now - cluster["lastSeenAt"]).total_seconds() / 60
            
            # Compute confidence
            confidence = compute_fusion_confidence(
                source_count=source_count,
                channel_count=channel_count,
                freshness_minutes=freshness_minutes
            )
            
            # Compute status
            status = compute_status(
                source_count=source_count,
                confidence=confidence,
                last_seen_at=cluster["lastSeenAt"]
            )
            
            # Get severity
            severity = max(
                get_severity(e.get("eventType", "virus"))
                for e in cluster["events"]
            )
            
            # Build fused document
            fused_doc = {
                "fusedId": self._make_fused_id(cluster["eventType"], cluster["lat"], cluster["lng"]),
                "eventType": cluster["eventType"],
                "center": {
                    "type": "Point",
                    "coordinates": [cluster["lng"], cluster["lat"]]
                },
                "lat": cluster["lat"],
                "lng": cluster["lng"],
                "title": cluster["title"],
                "firstSeenAt": cluster["firstSeenAt"],
                "lastSeenAt": cluster["lastSeenAt"],
                "status": status,
                "sourceCount": source_count,
                "sourceChannels": source_channels,
                "channelCount": channel_count,
                "messageIds": [
                    e.get("source", {}).get("messageId")
                    for e in cluster["events"]
                    if e.get("source", {}).get("messageId") is not None
                ],
                "confidence": confidence,
                "severity": severity,
                "score": confidence,  # For now, same as confidence
                "updatedAt": now
            }
            
            await self.repo.upsert_fused_event(fused_doc)
            fused_count += 1
        
        # Expire old events
        expired = await self.repo.expire_old_events(180)
        
        logger.info(f"Fusion engine: {fused_count} fused, {expired} expired")
        return {"ok": True, "fused": fused_count, "expired": expired}
