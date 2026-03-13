"""
Geo Stats Service
Aggregated statistics for places, hours, days
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


async def get_place_stats(db, days: int = 30, limit: int = 20) -> Dict:
    """
    Get top places by mention frequency.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$group": {
            "_id": "$title",
            "count": {"$sum": 1},
            "lat": {"$first": "$location.lat"},
            "lng": {"$first": "$location.lng"},
            "eventType": {"$first": "$eventType"},
            "lastSeen": {"$max": "$createdAt"}
        }},
        {"$sort": {"count": -1}},
        {"$limit": limit}
    ]
    
    items = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        items.append({
            "title": doc["_id"],
            "count": doc["count"],
            "lat": doc.get("lat"),
            "lng": doc.get("lng"),
            "eventType": doc.get("eventType"),
            "lastSeen": doc.get("lastSeen")
        })
    
    return {"ok": True, "items": items, "days": days}


async def get_hourly_stats(db, days: int = 7) -> Dict:
    """
    Get event distribution by hour of day.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$project": {
            "hour": {"$hour": "$createdAt"}
        }},
        {"$group": {
            "_id": "$hour",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    # Initialize all hours
    hours = {h: 0 for h in range(24)}
    
    async for doc in db.tg_geo_events.aggregate(pipeline):
        hours[doc["_id"]] = doc["count"]
    
    items = [{"hour": h, "count": c} for h, c in hours.items()]
    
    # Find peak hours
    sorted_hours = sorted(items, key=lambda x: x["count"], reverse=True)
    peak_hours = [h["hour"] for h in sorted_hours[:3] if h["count"] > 0]
    
    return {
        "ok": True,
        "items": items,
        "peakHours": peak_hours,
        "days": days
    }


async def get_weekday_stats(db, days: int = 30) -> Dict:
    """
    Get event distribution by day of week.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$project": {
            "dayOfWeek": {"$dayOfWeek": "$createdAt"}  # 1=Sunday, 7=Saturday
        }},
        {"$group": {
            "_id": "$dayOfWeek",
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    day_names = ["", "Неділя", "Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота"]
    
    # Initialize all days
    days_map = {i: 0 for i in range(1, 8)}
    
    async for doc in db.tg_geo_events.aggregate(pipeline):
        days_map[doc["_id"]] = doc["count"]
    
    items = [{"day": i, "name": day_names[i], "count": days_map[i]} for i in range(1, 8)]
    
    # Find peak days
    sorted_days = sorted(items, key=lambda x: x["count"], reverse=True)
    peak_days = [d["day"] for d in sorted_days[:3] if d["count"] > 0]
    
    return {
        "ok": True,
        "items": items,
        "peakDays": peak_days
    }


async def get_district_stats(db, days: int = 30) -> Dict:
    """
    Get event distribution by district (from tags).
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$unwind": "$tags"},
        {"$match": {"tags": {"$in": ["center", "podil", "pechersk", "obolon", "darnytsia"]}}},
        {"$group": {
            "_id": "$tags",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    district_names = {
        "center": "Центр",
        "podil": "Поділ",
        "pechersk": "Печерськ",
        "obolon": "Оболонь",
        "darnytsia": "Дарниця"
    }
    
    items = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        items.append({
            "district": doc["_id"],
            "name": district_names.get(doc["_id"], doc["_id"]),
            "count": doc["count"]
        })
    
    return {"ok": True, "items": items}


async def get_full_stats(db, days: int = 30) -> Dict:
    """
    Get comprehensive statistics.
    """
    places = await get_place_stats(db, days, limit=10)
    hourly = await get_hourly_stats(db, days)
    weekday = await get_weekday_stats(db, days)
    district = await get_district_stats(db, days)
    
    return {
        "ok": True,
        "topPlaces": places.get("items", []),
        "hourly": hourly.get("items", []),
        "peakHours": hourly.get("peakHours", []),
        "weekday": weekday.get("items", []),
        "peakDays": weekday.get("peakDays", []),
        "districts": district.get("items", []),
        "days": days
    }
