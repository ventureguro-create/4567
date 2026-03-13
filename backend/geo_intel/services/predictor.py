"""
Geo Predictor Service
Simple statistical prediction without ML
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


async def predict_hotspots(db, days: int = 30, limit: int = 10) -> Dict:
    """
    Predict likely hotspots based on historical frequency.
    
    Simple formula:
    probability = (count_7d * 0.5) + (weekday_match * 0.3) + (hour_match * 0.2)
    """
    now = datetime.now(timezone.utc)
    since_30d = now - timedelta(days=30)
    since_7d = now - timedelta(days=7)
    
    current_weekday = now.weekday() + 2  # MongoDB: 1=Sunday, Python: 0=Monday
    if current_weekday > 7:
        current_weekday -= 7
    current_hour = now.hour
    
    # Get 30d stats
    pipeline_30d = [
        {"$match": {"createdAt": {"$gte": since_30d}}},
        {"$group": {
            "_id": "$title",
            "count30d": {"$sum": 1},
            "lat": {"$first": "$location.lat"},
            "lng": {"$first": "$location.lng"},
            "eventType": {"$first": "$eventType"}
        }},
        {"$match": {"count30d": {"$gte": 2}}},
        {"$sort": {"count30d": -1}},
        {"$limit": 50}
    ]
    
    places_30d = {}
    async for doc in db.tg_geo_events.aggregate(pipeline_30d):
        places_30d[doc["_id"]] = {
            "count30d": doc["count30d"],
            "lat": doc.get("lat"),
            "lng": doc.get("lng"),
            "eventType": doc.get("eventType")
        }
    
    # Get 7d stats
    pipeline_7d = [
        {"$match": {"createdAt": {"$gte": since_7d}}},
        {"$group": {
            "_id": "$title",
            "count7d": {"$sum": 1}
        }}
    ]
    
    counts_7d = {}
    async for doc in db.tg_geo_events.aggregate(pipeline_7d):
        counts_7d[doc["_id"]] = doc["count7d"]
    
    # Get weekday patterns
    pipeline_weekday = [
        {"$match": {"createdAt": {"$gte": since_30d}}},
        {"$project": {
            "title": 1,
            "dayOfWeek": {"$dayOfWeek": "$createdAt"}
        }},
        {"$match": {"dayOfWeek": current_weekday}},
        {"$group": {
            "_id": "$title",
            "weekdayCount": {"$sum": 1}
        }}
    ]
    
    weekday_counts = {}
    async for doc in db.tg_geo_events.aggregate(pipeline_weekday):
        weekday_counts[doc["_id"]] = doc["weekdayCount"]
    
    # Get hourly patterns (±2 hours)
    pipeline_hour = [
        {"$match": {"createdAt": {"$gte": since_30d}}},
        {"$project": {
            "title": 1,
            "hour": {"$hour": "$createdAt"}
        }},
        {"$match": {"hour": {"$gte": max(0, current_hour - 2), "$lte": min(23, current_hour + 2)}}},
        {"$group": {
            "_id": "$title",
            "hourCount": {"$sum": 1}
        }}
    ]
    
    hour_counts = {}
    async for doc in db.tg_geo_events.aggregate(pipeline_hour):
        hour_counts[doc["_id"]] = doc["hourCount"]
    
    # Calculate predictions
    predictions = []
    
    for title, data in places_30d.items():
        count_30d = data["count30d"]
        count_7d = counts_7d.get(title, 0)
        weekday_match = weekday_counts.get(title, 0)
        hour_match = hour_counts.get(title, 0)
        
        # Normalize
        max_7d = max(counts_7d.values()) if counts_7d else 1
        max_weekday = max(weekday_counts.values()) if weekday_counts else 1
        max_hour = max(hour_counts.values()) if hour_counts else 1
        
        # Calculate probability
        prob_7d = (count_7d / max_7d) * 0.5 if max_7d > 0 else 0
        prob_weekday = (weekday_match / max_weekday) * 0.3 if max_weekday > 0 else 0
        prob_hour = (hour_match / max_hour) * 0.2 if max_hour > 0 else 0
        
        probability = min(1.0, prob_7d + prob_weekday + prob_hour)
        
        if probability > 0.1:  # Filter low probability
            predictions.append({
                "title": title,
                "lat": data.get("lat"),
                "lng": data.get("lng"),
                "eventType": data.get("eventType"),
                "probability": round(probability, 2),
                "count30d": count_30d,
                "count7d": count_7d,
                "weekdayMatches": weekday_match,
                "hourMatches": hour_match,
                "confidence": "high" if probability >= 0.6 else "medium" if probability >= 0.3 else "low"
            })
    
    # Sort by probability
    predictions.sort(key=lambda x: x["probability"], reverse=True)
    predictions = predictions[:limit]
    
    return {
        "ok": True,
        "predictions": predictions,
        "context": {
            "currentWeekday": current_weekday,
            "currentHour": current_hour,
            "analyzedDays": 30
        }
    }


async def get_place_prediction(db, title: str) -> Dict:
    """
    Get prediction for a specific place.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    
    # Get historical data
    pipeline = [
        {"$match": {"title": title, "createdAt": {"$gte": since}}},
        {"$project": {
            "hour": {"$hour": "$createdAt"},
            "dayOfWeek": {"$dayOfWeek": "$createdAt"}
        }},
        {"$group": {
            "_id": None,
            "hours": {"$push": "$hour"},
            "days": {"$push": "$dayOfWeek"},
            "count": {"$sum": 1}
        }}
    ]
    
    result = await db.tg_geo_events.aggregate(pipeline).to_list(1)
    
    if not result:
        return {"ok": True, "title": title, "prediction": None, "reason": "No data"}
    
    data = result[0]
    hours = data.get("hours", [])
    days = data.get("days", [])
    count = data.get("count", 0)
    
    # Calculate peak hours
    hour_freq = {}
    for h in hours:
        hour_freq[h] = hour_freq.get(h, 0) + 1
    
    top_hours = sorted(hour_freq.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Calculate peak days
    day_freq = {}
    for d in days:
        day_freq[d] = day_freq.get(d, 0) + 1
    
    top_days = sorted(day_freq.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # Simple probability
    base_prob = min(1.0, count / 30)  # Higher count = higher base probability
    
    return {
        "ok": True,
        "title": title,
        "count30d": count,
        "topHours": [h[0] for h in top_hours],
        "topDays": [d[0] for d in top_days],
        "probability": round(base_prob, 2),
        "prediction": f"Ймовірність появи: {int(base_prob * 100)}%"
    }
