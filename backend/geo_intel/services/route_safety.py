"""
Route Safety Engine
Analyzes routes for risk zones and suggests safer alternatives
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple

from ..utils.geo_distance import haversine_distance
from ..config.event_types import get_avoidance_radius, get_severity

logger = logging.getLogger(__name__)


async def check_route_safety(
    db,
    route_points: List[Dict],
    days: int = 3
) -> Dict:
    """
    Check if a route passes through risk zones.
    
    Args:
        db: Database connection
        route_points: List of {lat, lng} points along the route
        days: Days to look back for events
    
    Returns:
        Safety analysis with hazards found
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    if not route_points or len(route_points) < 2:
        return {
            "ok": False,
            "error": "Route must have at least 2 points"
        }
    
    # Get all recent events
    cursor = db.tg_geo_events.find(
        {"createdAt": {"$gte": since}},
        {"_id": 0}
    )
    events = await cursor.to_list(2000)
    
    if not events:
        return {
            "ok": True,
            "isSafe": True,
            "hazards": [],
            "riskScore": 0,
            "message": "Маршрут безпечний"
        }
    
    # Check each route point against events
    hazards = []
    total_risk = 0
    
    for point in route_points:
        plat = point.get("lat")
        plng = point.get("lng")
        
        if plat is None or plng is None:
            continue
        
        for event in events:
            loc = event.get("location", {})
            elat = loc.get("lat")
            elng = loc.get("lng")
            
            if elat is None or elng is None:
                continue
            
            # Calculate distance
            dist = haversine_distance(plat, plng, elat, elng)
            
            # Get avoidance radius for this event type
            event_type = event.get("eventType", "virus")
            avoidance = get_avoidance_radius(event_type)
            
            # Check if within avoidance zone
            if dist <= avoidance:
                severity = get_severity(event_type)
                
                # Check if we already have this hazard
                existing = next(
                    (h for h in hazards if h.get("eventId") == event.get("dedupeKey")),
                    None
                )
                
                if not existing:
                    hazards.append({
                        "eventId": event.get("dedupeKey"),
                        "eventType": event_type,
                        "title": event.get("title", ""),
                        "lat": elat,
                        "lng": elng,
                        "distance": round(dist),
                        "avoidanceRadius": avoidance,
                        "severity": severity,
                        "routePointLat": plat,
                        "routePointLng": plng
                    })
                    total_risk += severity
    
    # Calculate overall risk score
    max_possible_risk = len(route_points) * 4  # Max severity is 4
    risk_score = min(1.0, total_risk / max_possible_risk) if max_possible_risk > 0 else 0
    
    # Determine safety status
    is_safe = len(hazards) == 0
    
    if risk_score >= 0.5:
        message = "⚠️ Маршрут проходить через небезпечні зони"
    elif risk_score >= 0.2:
        message = "⚡ Маршрут має деякі ризики"
    elif len(hazards) > 0:
        message = "ℹ️ Маршрут має незначні ризики"
    else:
        message = "✅ Маршрут безпечний"
    
    return {
        "ok": True,
        "isSafe": is_safe,
        "hazards": hazards,
        "hazardCount": len(hazards),
        "riskScore": round(risk_score, 2),
        "totalSeverity": total_risk,
        "message": message,
        "routePoints": len(route_points)
    }


async def suggest_avoidance(
    db,
    start: Dict,
    end: Dict,
    days: int = 3
) -> Dict:
    """
    Suggest points to avoid based on risk zones.
    
    Args:
        db: Database connection
        start: {lat, lng} start point
        end: {lat, lng} end point
        days: Days to look back
    
    Returns:
        List of zones to avoid
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    start_lat = start.get("lat")
    start_lng = start.get("lng")
    end_lat = end.get("lat")
    end_lng = end.get("lng")
    
    if None in [start_lat, start_lng, end_lat, end_lng]:
        return {"ok": False, "error": "Invalid start/end points"}
    
    # Calculate bounding box
    min_lat = min(start_lat, end_lat) - 0.01
    max_lat = max(start_lat, end_lat) + 0.01
    min_lng = min(start_lng, end_lng) - 0.01
    max_lng = max(start_lng, end_lng) + 0.01
    
    # Get events in bounding box
    cursor = db.tg_geo_events.find({
        "createdAt": {"$gte": since},
        "location.lat": {"$gte": min_lat, "$lte": max_lat},
        "location.lng": {"$gte": min_lng, "$lte": max_lng}
    }, {"_id": 0})
    
    events = await cursor.to_list(500)
    
    # Build avoidance zones
    avoidance_zones = []
    
    for event in events:
        loc = event.get("location", {})
        elat = loc.get("lat")
        elng = loc.get("lng")
        event_type = event.get("eventType", "virus")
        
        if elat is None or elng is None:
            continue
        
        avoidance = get_avoidance_radius(event_type)
        severity = get_severity(event_type)
        
        # Only include significant hazards
        if severity >= 2:
            avoidance_zones.append({
                "lat": elat,
                "lng": elng,
                "radius": avoidance,
                "eventType": event_type,
                "severity": severity,
                "title": event.get("title", "")
            })
    
    # Sort by severity
    avoidance_zones.sort(key=lambda x: x["severity"], reverse=True)
    
    return {
        "ok": True,
        "start": start,
        "end": end,
        "avoidanceZones": avoidance_zones,
        "zoneCount": len(avoidance_zones),
        "boundingBox": {
            "minLat": min_lat,
            "maxLat": max_lat,
            "minLng": min_lng,
            "maxLng": max_lng
        }
    }


async def get_safest_direction(
    db,
    lat: float,
    lng: float,
    radius_m: int = 1000,
    days: int = 3
) -> Dict:
    """
    Determine safest direction to move from current location.
    Divides area into 8 sectors (N, NE, E, SE, S, SW, W, NW).
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    
    # Calculate bounding box
    lat_delta = radius_m / 111000
    lng_delta = radius_m / (111000 * 0.65)
    
    cursor = db.tg_geo_events.find({
        "createdAt": {"$gte": since},
        "location.lat": {"$gte": lat - lat_delta, "$lte": lat + lat_delta},
        "location.lng": {"$gte": lng - lng_delta, "$lte": lng + lng_delta}
    }, {"_id": 0})
    
    events = await cursor.to_list(500)
    
    # Initialize sectors
    sectors = {
        "N": {"risk": 0, "count": 0, "bearing": 0},
        "NE": {"risk": 0, "count": 0, "bearing": 45},
        "E": {"risk": 0, "count": 0, "bearing": 90},
        "SE": {"risk": 0, "count": 0, "bearing": 135},
        "S": {"risk": 0, "count": 0, "bearing": 180},
        "SW": {"risk": 0, "count": 0, "bearing": 225},
        "W": {"risk": 0, "count": 0, "bearing": 270},
        "NW": {"risk": 0, "count": 0, "bearing": 315}
    }
    
    import math
    
    for event in events:
        loc = event.get("location", {})
        elat = loc.get("lat")
        elng = loc.get("lng")
        
        if elat is None or elng is None:
            continue
        
        # Calculate bearing from current location
        dlat = elat - lat
        dlng = elng - lng
        bearing = math.degrees(math.atan2(dlng, dlat))
        if bearing < 0:
            bearing += 360
        
        # Determine sector
        sector_idx = round(bearing / 45) % 8
        sector_names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
        sector = sector_names[sector_idx]
        
        severity = get_severity(event.get("eventType", "virus"))
        sectors[sector]["risk"] += severity
        sectors[sector]["count"] += 1
    
    # Find safest sector
    safest = min(sectors.items(), key=lambda x: x[1]["risk"])
    most_dangerous = max(sectors.items(), key=lambda x: x[1]["risk"])
    
    return {
        "ok": True,
        "currentLocation": {"lat": lat, "lng": lng},
        "sectors": sectors,
        "safestDirection": safest[0],
        "safestBearing": safest[1]["bearing"],
        "dangerousDirection": most_dangerous[0],
        "dangerousBearing": most_dangerous[1]["bearing"],
        "radius": radius_m
    }
