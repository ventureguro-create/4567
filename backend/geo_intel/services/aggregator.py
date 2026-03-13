"""
Geo Intel Aggregator
Builds map points, top places, heatmap data
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


async def get_map_points(
    db,
    days: int = 7,
    event_type: Optional[str] = None,
    limit: int = 500,
    actor_id: str = "anon"
) -> Dict:
    """Get geo events as map points from multiple sources"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    query = {
        "createdAt": {"$gte": since},
        "location": {"$ne": None}  # Only events with coordinates
    }
    
    if event_type and event_type != "all":
        query["eventType"] = event_type
    
    items = []
    
    # 1. Get from tg_geo_events (channel data)
    cursor = db.tg_geo_events.find(query, {"_id": 0}).sort("createdAt", -1).limit(limit)
    
    async for event in cursor:
        loc = event.get("location")
        if not loc:
            continue
        
        items.append({
            "id": event.get("dedupeKey"),
            "eventType": event.get("eventType", "place"),
            "title": event.get("title", ""),
            "addressText": event.get("addressText", ""),
            "lat": loc.get("lat"),
            "lng": loc.get("lng"),
            "precision": event.get("geoPrecision", "unknown"),
            "source": event.get("source", {}),
            "metrics": event.get("metrics", {}),
            "createdAt": event.get("createdAt"),
            "evidenceText": event.get("evidenceText", "")[:200]
        })
    
    # 2. Get from geo_events (user reports)
    user_query = {
        "createdAt": {"$gte": since},
        "reportId": {"$exists": True}  # User reports have reportId
    }
    if event_type and event_type != "all":
        user_query["eventType"] = event_type
    
    cursor2 = db.geo_events.find(user_query, {"_id": 0}).sort("createdAt", -1).limit(limit)
    
    async for event in cursor2:
        loc = event.get("location")
        lat = event.get("lat") or (loc.get("coordinates", [0, 0])[1] if loc else None)
        lng = event.get("lng") or (loc.get("coordinates", [0, 0])[0] if loc else None)
        
        if not lat or not lng:
            continue
        
        items.append({
            "id": event.get("reportId"),
            "eventType": event.get("eventType", "other"),
            "title": event.get("title", "Сигнал"),
            "addressText": event.get("addressText", ""),
            "lat": lat,
            "lng": lng,
            "precision": "user_report",
            "source": event.get("source", {"type": "user_report"}),
            "metrics": event.get("metrics", {}),
            "createdAt": event.get("createdAt"),
            "evidenceText": "",
            "truthScore": event.get("truthScore", 0),
            "confidenceLevel": event.get("confidenceLevel", "low"),
            "confirmationCount": event.get("confirmationCount", 0)
        })
    
    # Sort combined by createdAt
    items.sort(key=lambda x: x.get("createdAt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    items = items[:limit]
    
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "points": items,  # Alias for frontend compatibility
        "filters": {"days": days, "eventType": event_type}
    }


async def get_top_places(
    db,
    days: int = 30,
    limit: int = 50,
    actor_id: str = "anon"
) -> Dict:
    """Get top places by frequency"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$group": {
            "_id": {"title": "$title", "eventType": "$eventType"},
            "count": {"$sum": 1},
            "lastSeen": {"$max": "$createdAt"},
            "totalViews": {"$sum": "$metrics.views"},
            "sampleLocation": {"$first": "$location"},
            "channels": {"$addToSet": "$source.username"}
        }},
        {"$sort": {"count": -1, "lastSeen": -1}},
        {"$limit": limit}
    ]
    
    items = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        items.append({
            "title": doc["_id"]["title"],
            "eventType": doc["_id"]["eventType"],
            "count": doc["count"],
            "lastSeen": doc["lastSeen"],
            "totalViews": doc["totalViews"],
            "location": doc.get("sampleLocation"),
            "channelCount": len(doc.get("channels", []))
        })
    
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "days": days
    }


async def get_heatmap_data(
    db,
    days: int = 7,
    actor_id: str = "anon"
) -> Dict:
    """Get heatmap data for density visualization"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {
            "createdAt": {"$gte": since},
            "location": {"$ne": None}
        }},
        {"$group": {
            "_id": {
                # Round to ~100m grid
                "lat": {"$round": [{"$multiply": ["$location.lat", 1000]}, 0]},
                "lng": {"$round": [{"$multiply": ["$location.lng", 1000]}, 0]}
            },
            "weight": {"$sum": 1}
        }}
    ]
    
    items = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        items.append({
            "lat": doc["_id"]["lat"] / 1000,
            "lng": doc["_id"]["lng"] / 1000,
            "weight": doc["weight"]
        })
    
    return {
        "ok": True,
        "items": items,
        "total": len(items)
    }


async def get_event_types_stats(db, days: int = 30) -> Dict:
    """Get event type distribution"""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$group": {
            "_id": "$eventType",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    items = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        items.append({
            "eventType": doc["_id"],
            "count": doc["count"]
        })
    
    return {"ok": True, "items": items}
