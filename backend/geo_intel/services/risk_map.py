"""
Risk Map Service
Generates risk zones based on event density and severity
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from ..config.event_types import get_severity

logger = logging.getLogger(__name__)


async def build_risk_map(
    db,
    days: int = 7,
    grid_precision: int = 3
) -> Dict:
    """
    Build risk map with severity-weighted zones.
    
    Risk formula:
    risk = (event_count * avg_severity * freshness_weight) / max_possible
    
    Args:
        db: Database connection
        days: How many days to analyze
        grid_precision: Decimal places for lat/lng grouping (3 = ~100m cells)
    
    Returns:
        Dict with risk zones
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    # Aggregate by grid cell
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$project": {
            "lat": {"$round": ["$location.lat", grid_precision]},
            "lng": {"$round": ["$location.lng", grid_precision]},
            "eventType": 1,
            "createdAt": 1
        }},
        {"$group": {
            "_id": {"lat": "$lat", "lng": "$lng"},
            "count": {"$sum": 1},
            "types": {"$push": "$eventType"},
            "lastSeen": {"$max": "$createdAt"}
        }}
    ]
    
    zones = []
    max_risk = 0
    
    async for doc in db.tg_geo_events.aggregate(pipeline):
        lat = doc["_id"]["lat"]
        lng = doc["_id"]["lng"]
        
        if lat is None or lng is None:
            continue
        
        count = doc["count"]
        types = doc["types"]
        last_seen = doc["lastSeen"]
        
        # Calculate average severity
        severities = [get_severity(t) for t in types]
        avg_severity = sum(severities) / len(severities) if severities else 2
        
        # Calculate freshness weight (newer = higher weight)
        if last_seen:
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            age_hours = (now - last_seen).total_seconds() / 3600
            freshness = max(0.2, 1 - (age_hours / (days * 24)))
        else:
            freshness = 0.2
        
        # Calculate raw risk score
        raw_risk = count * avg_severity * freshness
        
        if raw_risk > max_risk:
            max_risk = raw_risk
        
        # Count by type
        type_counts = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1
        
        zones.append({
            "lat": lat,
            "lng": lng,
            "count": count,
            "avgSeverity": round(avg_severity, 2),
            "freshness": round(freshness, 2),
            "rawRisk": round(raw_risk, 2),
            "dominantType": max(type_counts, key=type_counts.get) if type_counts else "virus",
            "typeCounts": type_counts,
            "lastSeen": last_seen.isoformat() if last_seen else None
        })
    
    # Normalize risk scores to 0-1
    for zone in zones:
        zone["riskScore"] = round(zone["rawRisk"] / max_risk, 2) if max_risk > 0 else 0
        
        # Risk level label
        if zone["riskScore"] >= 0.8:
            zone["riskLevel"] = "critical"
        elif zone["riskScore"] >= 0.6:
            zone["riskLevel"] = "high"
        elif zone["riskScore"] >= 0.4:
            zone["riskLevel"] = "medium"
        elif zone["riskScore"] >= 0.2:
            zone["riskLevel"] = "low"
        else:
            zone["riskLevel"] = "minimal"
    
    # Sort by risk
    zones.sort(key=lambda x: x["riskScore"], reverse=True)
    
    return {
        "ok": True,
        "zones": zones,
        "totalZones": len(zones),
        "maxRawRisk": round(max_risk, 2),
        "days": days,
        "gridPrecision": grid_precision
    }


async def get_risk_at_location(
    db,
    lat: float,
    lng: float,
    radius_m: int = 500,
    days: int = 7
) -> Dict:
    """
    Get risk score for a specific location.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    # Calculate bounding box
    lat_delta = radius_m / 111000
    lng_delta = radius_m / (111000 * 0.65)
    
    # Find events in area
    cursor = db.tg_geo_events.find({
        "createdAt": {"$gte": since},
        "location.lat": {"$gte": lat - lat_delta, "$lte": lat + lat_delta},
        "location.lng": {"$gte": lng - lng_delta, "$lte": lng + lng_delta}
    }, {"_id": 0})
    
    events = await cursor.to_list(500)
    
    if not events:
        return {
            "ok": True,
            "lat": lat,
            "lng": lng,
            "riskScore": 0,
            "riskLevel": "minimal",
            "eventCount": 0,
            "reason": "No events in area"
        }
    
    # Calculate risk
    total_severity = 0
    for e in events:
        total_severity += get_severity(e.get("eventType", "virus"))
    
    avg_severity = total_severity / len(events)
    
    # Simple risk formula
    risk_score = min(1.0, (len(events) * avg_severity) / 50)
    
    if risk_score >= 0.8:
        risk_level = "critical"
    elif risk_score >= 0.6:
        risk_level = "high"
    elif risk_score >= 0.4:
        risk_level = "medium"
    elif risk_score >= 0.2:
        risk_level = "low"
    else:
        risk_level = "minimal"
    
    return {
        "ok": True,
        "lat": lat,
        "lng": lng,
        "riskScore": round(risk_score, 2),
        "riskLevel": risk_level,
        "eventCount": len(events),
        "avgSeverity": round(avg_severity, 2),
        "radius": radius_m
    }
