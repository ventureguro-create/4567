"""
Geo Intel Event Builder
Processes tg_posts and creates tg_geo_events
"""
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from .extractor import extract_places, extract_entities, contains_denied
from .geocoder import get_geocoder

logger = logging.getLogger(__name__)


async def build_geo_events_for_channel(
    db,
    username: str,
    days: int = 7,
    limit: int = 200,
    actor_id: str = "anon"
) -> dict:
    """
    Build geo events from posts of a specific channel.
    Reads from tg_posts (read-only), writes to tg_geo_events.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    # Read posts from channel
    posts = await db.tg_posts.find({
        "username": username,
        "date": {"$gte": since.isoformat()}
    }).sort("date", -1).limit(limit).to_list(limit)
    
    if not posts:
        logger.info(f"No posts found for {username} in last {days} days")
        return {"created": 0, "skipped": 0, "channel": username}
    
    geocoder = get_geocoder()
    created = 0
    skipped = 0
    
    for post in posts:
        text = (post.get("text") or "").strip()
        if not text or len(text) < 20:
            continue
        
        # Skip dangerous content
        if contains_denied(text):
            skipped += 1
            continue
        
        # Extract place candidates
        candidates = extract_places(text)
        if not candidates:
            continue
        
        # Extract additional entities
        entities = extract_entities(text)
        
        for candidate in candidates:
            # Try to geocode
            geo_result = await geocoder.geocode(candidate["addressText"])
            
            # Create event document
            message_id = post.get("messageId", 0)
            post_date = post.get("date")
            if isinstance(post_date, str):
                try:
                    post_date = datetime.fromisoformat(post_date.replace('Z', '+00:00'))
                except:
                    post_date = datetime.now(timezone.utc)
            
            # Dedupe key
            dedupe_key = hashlib.sha256(
                f"{actor_id}:{username}:{message_id}:{candidate['title'].lower()}".encode()
            ).hexdigest()[:32]
            
            event_doc = {
                "actorId": actor_id,
                "dedupeKey": dedupe_key,
                "source": {
                    "username": username,
                    "messageId": message_id,
                    "date": post_date
                },
                "eventType": candidate.get("eventType", "place"),
                "title": candidate["title"],
                "addressText": candidate["addressText"],
                "evidenceText": text[:500],
                "entities": entities,
                "tags": [e["value"] for e in entities if e["kind"] == "tag"],
                "metrics": {
                    "views": post.get("views", 0),
                    "forwards": post.get("forwards", 0),
                    "replies": post.get("replies", 0)
                },
                "score": 0.0,
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
            }
            
            # Add location if geocoded
            if geo_result:
                lat, lng, precision = geo_result
                event_doc["location"] = {"lat": lat, "lng": lng}
                event_doc["geoPrecision"] = precision
            else:
                event_doc["location"] = None
                event_doc["geoPrecision"] = "unknown"
            
            # Upsert (dedupe by key)
            try:
                result = await db.tg_geo_events.update_one(
                    {"dedupeKey": dedupe_key},
                    {"$setOnInsert": event_doc},
                    upsert=True
                )
                if result.upserted_id:
                    created += 1
            except Exception as e:
                logger.warning(f"Event insert error: {e}")
                continue
    
    # Update channel scan timestamp
    await db.tg_radar_channels.update_one(
        {"username": username},
        {"$set": {"lastScanAt": datetime.now(timezone.utc)}},
        upsert=False
    )
    
    logger.info(f"Built {created} geo events for {username} (skipped: {skipped})")
    return {"created": created, "skipped": skipped, "channel": username}


async def rebuild_all_channels(db, days: int = 7) -> dict:
    """Rebuild geo events for all enabled radar channels"""
    channels = await db.tg_radar_channels.find({"enabled": True}).to_list(100)
    
    total_created = 0
    total_skipped = 0
    
    for channel in channels:
        result = await build_geo_events_for_channel(
            db,
            username=channel["username"],
            days=days
        )
        total_created += result["created"]
        total_skipped += result["skipped"]
    
    return {
        "channels": len(channels),
        "created": total_created,
        "skipped": total_skipped
    }
