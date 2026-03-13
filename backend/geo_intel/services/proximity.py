"""
Geo Intel Proximity Service
Radar/nearby events queries with enhanced data for UI
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from ..utils.geo_distance import haversine_distance
from ..utils.freshness import freshness_score, freshness_label

logger = logging.getLogger(__name__)


async def get_nearby_events(
    db,
    lat: float,
    lng: float,
    radius_m: int = 500,
    days: int = 7,
    limit: int = 50
) -> Dict:
    """
    Get events within radius of a point with full UI data.
    
    Response includes:
    - userLocation with coordinates and radius
    - items with distanceMeters, isInsideRadius, freshnessScore, minutesAgo
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    try:
        # Try geospatial query first (GeoJSON format)
        cursor = db.tg_geo_events.find({
            "createdAt": {"$gte": since},
            "location": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                    "$maxDistance": radius_m * 2
                }
            }
        }, {"_id": 0}).limit(limit * 3)
        
        items = []
        async for event in cursor:
            loc = event.get("location", {})
            
            # Handle both GeoJSON and flat formats
            if "coordinates" in loc:
                event_lng = loc["coordinates"][0]
                event_lat = loc["coordinates"][1]
            else:
                event_lat = loc.get("lat")
                event_lng = loc.get("lng")
            
            if event_lat is None or event_lng is None:
                continue
            
            # Calculate actual distance using Haversine
            distance = haversine_distance(lat, lng, event_lat, event_lng)
            
            # Include events up to 2x radius for context
            if distance <= radius_m * 2:
                created_at = event.get("createdAt")
                
                # Handle timezone
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                
                minutes_ago = int((now - created_at).total_seconds() / 60) if created_at else 999
                fresh_score = freshness_score(created_at) if created_at else 0.1
                
                items.append({
                    "id": event.get("dedupeKey"),
                    "eventType": event.get("eventType", "place"),
                    "title": event.get("title", ""),
                    "addressText": event.get("addressText", ""),
                    "lat": event_lat,
                    "lng": event_lng,
                    "distanceMeters": round(distance),
                    "isInsideRadius": distance <= radius_m,
                    "createdAt": created_at.isoformat() if created_at else None,
                    "minutesAgo": minutes_ago,
                    "confidence": event.get("score", 0.5),
                    "freshnessScore": round(fresh_score, 2),
                    "freshnessLabel": freshness_label(fresh_score),
                    "source": event.get("source", {}),
                    "evidenceText": event.get("evidenceText", "")[:200],
                    "metrics": event.get("metrics", {})
                })
        
        # Sort by distance
        items.sort(key=lambda x: x.get("distanceMeters", 99999))
        
        # Limit results
        items = items[:limit]
        
        # Count inside radius
        inside_count = sum(1 for i in items if i.get("isInsideRadius"))
        
        return {
            "ok": True,
            "userLocation": {
                "lat": lat,
                "lng": lng,
                "radius": radius_m
            },
            "count": len(items),
            "insideRadius": inside_count,
            "items": items
        }
        
    except Exception as e:
        logger.error(f"Proximity query error: {e}")
        return {
            "ok": False,
            "error": str(e),
            "userLocation": {"lat": lat, "lng": lng, "radius": radius_m},
            "count": 0,
            "insideRadius": 0,
            "items": []
        }


async def evaluate_radar_alert(
    db,
    lat: float,
    lng: float,
    radius_m: int = 500,
    hours: int = 1
) -> Dict:
    """
    Evaluate if radar should trigger alert.
    Returns alert status and recent events.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    result = await get_nearby_events(db, lat, lng, radius_m, days=1, limit=10)
    
    if not result.get("ok"):
        return {"alert": False, "reason": "query_error"}
    
    # Filter to only recent events
    recent_events = [
        e for e in result.get("items", [])
        if e.get("createdAt") and e["createdAt"] >= since
    ]
    
    if not recent_events:
        return {"alert": False, "count": 0, "events": []}
    
    return {
        "alert": True,
        "count": len(recent_events),
        "events": recent_events[:5],
        "message": f"{len(recent_events)} подій за останню годину в радіусі {radius_m}м"
    }
