"""
Risk Zone Engine - Builds dynamic risk zones from fused events
"""
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any

from ..utils.geo_distance import haversine_distance

logger = logging.getLogger(__name__)

# Clustering parameters
CLUSTER_DISTANCE_M = 300  # Events within 300m are clustered
MIN_EVENTS_FOR_ZONE = 1   # Minimum events to create a zone


class RiskZoneEngine:
    """Engine for building dynamic risk zones from fused events"""
    
    def __init__(self, repo):
        self.repo = repo
    
    def _zone_id(self, lat: float, lng: float, event_type: str) -> str:
        """Generate unique zone ID"""
        return f"{event_type}_{round(lat, 3)}_{round(lng, 3)}"
    
    def _calculate_risk_score(
        self,
        event_count: int,
        confidence_avg: float,
        age_minutes: float,
        severity_avg: float
    ) -> float:
        """
        Calculate risk score (0-1) for a zone
        
        Formula:
        - eventDensity (45%): how many events in cluster
        - confidenceAvg (25%): average confidence of events
        - freshness (20%): how recent are events
        - severity (10%): average event severity
        """
        # Density score (max at 8 events)
        density = min(event_count / 8, 1.0)
        
        # Freshness score (decay over 90 minutes)
        freshness = max(0, 1 - age_minutes / 90)
        
        # Severity normalized (1-4 range to 0-1)
        severity_norm = (severity_avg - 1) / 3  # 1->0, 4->1
        
        risk_score = (
            density * 0.45 +
            confidence_avg * 0.25 +
            freshness * 0.20 +
            severity_norm * 0.10
        )
        
        return round(min(1.0, max(0, risk_score)), 2)
    
    def _get_status(self, risk_score: float) -> str:
        """Get zone status based on risk score"""
        if risk_score >= 0.75:
            return "HIGH"
        elif risk_score >= 0.5:
            return "MEDIUM"
        elif risk_score >= 0.3:
            return "LOW"
        else:
            return "MINIMAL"
    
    async def rebuild(self) -> Dict[str, Any]:
        """Rebuild all risk zones from fused events"""
        events = await self.repo.get_active_fused_events()
        
        if not events:
            return {"ok": True, "zones_created": 0, "message": "No active fused events"}
        
        # Sort by time for proper clustering
        events.sort(key=lambda x: x.get("lastSeenAt", datetime.min))
        
        # Cluster events by location and type
        clusters = []
        
        for e in events:
            center = e.get("center", {})
            coords = center.get("coordinates", [])
            if len(coords) < 2:
                continue
            
            lng, lat = coords[0], coords[1]
            etype = e.get("eventType", "unknown")
            
            # Try to match to existing cluster
            matched = False
            for cluster in clusters:
                dist = haversine_distance(
                    lat, lng,
                    cluster["lat"], cluster["lng"]
                )
                
                if dist < CLUSTER_DISTANCE_M and cluster["eventType"] == etype:
                    cluster["events"].append(e)
                    # Update cluster center (weighted average)
                    n = len(cluster["events"])
                    cluster["lat"] = (cluster["lat"] * (n-1) + lat) / n
                    cluster["lng"] = (cluster["lng"] * (n-1) + lng) / n
                    matched = True
                    break
            
            if not matched:
                clusters.append({
                    "lat": lat,
                    "lng": lng,
                    "eventType": etype,
                    "events": [e]
                })
        
        # Build zones from clusters
        zones_created = 0
        now = datetime.now(timezone.utc)
        
        for cluster in clusters:
            events_list = cluster["events"]
            event_count = len(events_list)
            
            if event_count < MIN_EVENTS_FOR_ZONE:
                continue
            
            # Calculate aggregated metrics
            confidence_avg = sum(
                e.get("confidence", 0.5) for e in events_list
            ) / event_count
            
            severity_avg = sum(
                e.get("severity", 2) for e in events_list
            ) / event_count
            
            # Get age of freshest event (handle naive/aware datetime)
            last_seen_times = []
            for e in events_list:
                ts = e.get("lastSeenAt", now)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                last_seen_times.append(ts)
            
            freshest = max(last_seen_times) if last_seen_times else now
            age_minutes = (now - freshest).total_seconds() / 60
            
            # Calculate risk score
            risk_score = self._calculate_risk_score(
                event_count,
                confidence_avg,
                age_minutes,
                severity_avg
            )
            
            # Determine radius based on event spread
            if event_count > 1:
                # Calculate max distance from center
                max_dist = 0
                for e in events_list:
                    coords = e.get("center", {}).get("coordinates", [])
                    if len(coords) >= 2:
                        dist = haversine_distance(
                            cluster["lat"], cluster["lng"],
                            coords[1], coords[0]
                        )
                        max_dist = max(max_dist, dist)
                radius = max(200, min(500, int(max_dist) + 100))
            else:
                radius = 250
            
            zone = {
                "zoneId": self._zone_id(
                    cluster["lat"],
                    cluster["lng"],
                    cluster["eventType"]
                ),
                "center": {
                    "type": "Point",
                    "coordinates": [cluster["lng"], cluster["lat"]]
                },
                "radiusMeters": radius,
                "eventType": cluster["eventType"],
                "eventCount": event_count,
                "confidence": round(confidence_avg, 2),
                "severity": round(severity_avg, 1),
                "riskScore": risk_score,
                "riskLevel": self._get_status(risk_score),
                "status": "ACTIVE",
                "lastEventAt": freshest,
                "updatedAt": now,
            }
            
            await self.repo.upsert_zone(zone)
            zones_created += 1
        
        # Expire old zones
        expired = await self.repo.expire_old_zones(max_age_minutes=120)
        
        logger.info(f"Risk zones rebuilt: {zones_created} created, {expired} expired")
        
        return {
            "ok": True,
            "zones_created": zones_created,
            "zones_expired": expired,
            "clusters_processed": len(clusters)
        }
