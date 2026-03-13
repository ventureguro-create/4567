"""
Geo Alert Subscriptions Service
Manages user subscriptions for proximity alerts
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


async def create_subscription(
    db,
    actor_id: str,
    telegram_chat_id: int,
    lat: float,
    lng: float,
    radius: int = 1000,
    event_types: List[str] = None
) -> Dict:
    """
    Create or update alert subscription.
    """
    if event_types is None:
        event_types = ["virus", "place", "food", "traffic"]
    
    doc = {
        "actorId": actor_id,
        "telegramChatId": telegram_chat_id,
        "lastLat": lat,
        "lastLng": lng,
        "radius": radius,
        "eventTypes": event_types,
        "enabled": True,
        "cooldownUntil": None,
        "lastAlertAt": None,
        "alertCount": 0,
        "updatedAt": datetime.now(timezone.utc)
    }
    
    try:
        result = await db.geo_alert_subscriptions.update_one(
            {"actorId": actor_id},
            {
                "$set": doc,
                "$setOnInsert": {"createdAt": datetime.now(timezone.utc)}
            },
            upsert=True
        )
        
        return {
            "ok": True,
            "actorId": actor_id,
            "subscribed": True,
            "upserted": result.upserted_id is not None
        }
    except Exception as e:
        logger.error(f"Subscription error: {e}")
        return {"ok": False, "error": str(e)}


async def update_location(db, actor_id: str, lat: float, lng: float) -> Dict:
    """
    Update user's last known location.
    """
    result = await db.geo_alert_subscriptions.update_one(
        {"actorId": actor_id},
        {
            "$set": {
                "lastLat": lat,
                "lastLng": lng,
                "updatedAt": datetime.now(timezone.utc)
            }
        }
    )
    
    return {
        "ok": True,
        "updated": result.modified_count > 0
    }


async def unsubscribe(db, actor_id: str) -> Dict:
    """
    Disable subscription.
    """
    result = await db.geo_alert_subscriptions.update_one(
        {"actorId": actor_id},
        {"$set": {"enabled": False, "updatedAt": datetime.now(timezone.utc)}}
    )
    
    return {"ok": True, "disabled": result.modified_count > 0}


async def get_subscription(db, actor_id: str) -> Optional[Dict]:
    """
    Get subscription by actor ID.
    """
    return await db.geo_alert_subscriptions.find_one(
        {"actorId": actor_id},
        {"_id": 0}
    )


async def get_active_subscriptions(db) -> List[Dict]:
    """
    Get all active subscriptions for worker.
    """
    cursor = db.geo_alert_subscriptions.find(
        {"enabled": True},
        {"_id": 0}
    )
    return await cursor.to_list(1000)


async def set_cooldown(db, actor_id: str, minutes: int = 30):
    """
    Set cooldown period after sending alert.
    """
    cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    
    await db.geo_alert_subscriptions.update_one(
        {"actorId": actor_id},
        {
            "$set": {
                "cooldownUntil": cooldown_until,
                "lastAlertAt": datetime.now(timezone.utc)
            },
            "$inc": {"alertCount": 1}
        }
    )


async def log_alert(db, subscription_id: str, event_id: str):
    """
    Log sent alert for deduplication.
    """
    await db.geo_alert_log.insert_one({
        "subscriptionId": subscription_id,
        "eventId": event_id,
        "sentAt": datetime.now(timezone.utc)
    })


async def was_alert_sent(db, subscription_id: str, event_id: str) -> bool:
    """
    Check if alert was already sent.
    """
    existing = await db.geo_alert_log.find_one({
        "subscriptionId": subscription_id,
        "eventId": event_id
    })
    return existing is not None
