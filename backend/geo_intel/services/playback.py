"""
Playback Service
Generates timeline frames for activity replay
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List

logger = logging.getLogger(__name__)


async def build_playback_frames(
    db,
    hours: int = 24,
    step_minutes: int = 30
) -> Dict:
    """
    Build playback frames for activity timeline.
    
    Args:
        db: Database connection
        hours: How many hours to look back
        step_minutes: Time step for each frame
    
    Returns:
        Dict with frames array, each frame has timestamp and events
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    
    # Get all events in range
    cursor = db.tg_geo_events.find(
        {"createdAt": {"$gte": start, "$lte": now}},
        {"_id": 0}
    ).sort("createdAt", 1)
    
    events = await cursor.to_list(5000)
    
    if not events:
        return {
            "ok": True,
            "frames": [],
            "totalEvents": 0,
            "hours": hours,
            "stepMinutes": step_minutes
        }
    
    # Build frames
    frames = []
    current = start
    
    while current < now:
        next_step = current + timedelta(minutes=step_minutes)
        
        # Find events in this time window
        frame_events = []
        for e in events:
            created = e.get("createdAt")
            if created is None:
                continue
            
            # Handle naive datetime
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            
            if current <= created < next_step:
                loc = e.get("location", {})
                frame_events.append({
                    "id": e.get("dedupeKey"),
                    "lat": loc.get("lat"),
                    "lng": loc.get("lng"),
                    "eventType": e.get("eventType", "virus"),
                    "title": e.get("title", ""),
                    "confidence": e.get("score", 0.5)
                })
        
        frames.append({
            "timestamp": current.isoformat(),
            "timestampLocal": current.strftime("%H:%M"),
            "eventCount": len(frame_events),
            "events": frame_events
        })
        
        current = next_step
    
    # Calculate cumulative events for each frame
    cumulative = []
    all_events_so_far = []
    
    for frame in frames:
        all_events_so_far.extend(frame["events"])
        cumulative.append({
            "timestamp": frame["timestamp"],
            "timestampLocal": frame["timestampLocal"],
            "newEvents": frame["eventCount"],
            "totalEvents": len(all_events_so_far),
            "events": frame["events"]
        })
    
    return {
        "ok": True,
        "frames": cumulative,
        "totalFrames": len(frames),
        "totalEvents": len(events),
        "hours": hours,
        "stepMinutes": step_minutes,
        "startTime": start.isoformat(),
        "endTime": now.isoformat()
    }


async def get_playback_summary(db, hours: int = 24) -> Dict:
    """
    Get summary statistics for playback period.
    """
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    
    # Count by hour
    pipeline = [
        {"$match": {"createdAt": {"$gte": start}}},
        {"$project": {
            "hour": {"$hour": "$createdAt"},
            "eventType": 1
        }},
        {"$group": {
            "_id": {"hour": "$hour", "type": "$eventType"},
            "count": {"$sum": 1}
        }}
    ]
    
    hourly_data = {}
    async for doc in db.tg_geo_events.aggregate(pipeline):
        hour = doc["_id"]["hour"]
        etype = doc["_id"]["type"]
        if hour not in hourly_data:
            hourly_data[hour] = {}
        hourly_data[hour][etype] = doc["count"]
    
    # Find peak hour
    peak_hour = max(hourly_data.keys(), key=lambda h: sum(hourly_data[h].values())) if hourly_data else None
    
    return {
        "ok": True,
        "hourlyBreakdown": hourly_data,
        "peakHour": peak_hour,
        "hours": hours
    }
