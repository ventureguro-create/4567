"""
Geo Alert Scheduler
Background worker for proximity alerts
Runs every 60 seconds, checks subscriptions, sends alerts
"""
import os
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional

from .proximity import get_nearby_events
from .notifier import (
    send_telegram_alert, 
    format_proximity_alert, 
    format_multiple_events_alert,
    get_confirmation_keyboard,
    get_multi_confirmation_keyboard
)
from .subscriptions import set_cooldown, log_alert, was_alert_sent

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("APP_BASE_URL", "https://radar-control-hub.preview.emergentagent.com")
COOLDOWN_MINUTES = 30
CHECK_INTERVAL_SECONDS = 60


class GeoAlertScheduler:
    """Background scheduler for proximity alerts"""
    
    def __init__(self, db):
        self.db = db
        self.running = False
        self.check_count = 0
        self.alert_count = 0
    
    async def check_subscription(self, sub: dict) -> int:
        """
        Check single subscription for alerts.
        Returns number of alerts sent.
        """
        actor_id = sub.get("actorId")
        chat_id = sub.get("telegramChatId")
        lat = sub.get("lastLat")
        lng = sub.get("lastLng")
        radius = sub.get("radius", 1000)
        event_types = sub.get("eventTypes", ["virus", "trash"])
        
        # Skip if no location
        if lat is None or lng is None:
            return 0
        
        # Skip if in cooldown
        cooldown_until = sub.get("cooldownUntil")
        if cooldown_until and cooldown_until > datetime.now(timezone.utc):
            return 0
        
        # Get nearby events (last 2 hours only for alerts)
        result = await get_nearby_events(
            self.db,
            lat=lat,
            lng=lng,
            radius_m=radius,
            days=1,  # Last day
            limit=20
        )
        
        if not result.get("ok"):
            return 0
        
        # Filter fresh events (last 2 hours) inside radius
        fresh_events = []
        for event in result.get("items", []):
            if not event.get("isInsideRadius"):
                continue
            
            # Only recent events (last 2 hours)
            minutes_ago = event.get("minutesAgo", 9999)
            if minutes_ago > 120:
                continue
            
            # Filter by event type
            if event.get("eventType") not in event_types:
                continue
            
            # Check if alert was already sent for this event
            event_id = event.get("id")
            if event_id and await was_alert_sent(self.db, actor_id, event_id):
                continue
            
            fresh_events.append(event)
        
        if not fresh_events:
            return 0
        
        # Send alert with confirmation buttons
        try:
            if len(fresh_events) == 1:
                # Single event alert with confirmation
                event = fresh_events[0]
                event_id = event.get("id", "unknown")
                text = format_proximity_alert(
                    event_type=event.get("eventType", "virus"),
                    title=event.get("title", "Невідомо"),
                    distance=event.get("distanceMeters", 0),
                    minutes_ago=event.get("minutesAgo", 0),
                    confidence=event.get("confidence", 0.5),
                    base_url=BASE_URL
                )
                keyboard = get_confirmation_keyboard(event_id)
            else:
                # Multiple events alert with confirmation
                event_ids = [e.get("id", "unknown") for e in fresh_events]
                text = format_multiple_events_alert(
                    events=fresh_events,
                    radius=radius,
                    base_url=BASE_URL
                )
                keyboard = get_multi_confirmation_keyboard(event_ids)
            
            result = await send_telegram_alert(chat_id, text, reply_markup=keyboard)
            
            if result.get("ok"):
                # Set cooldown
                await set_cooldown(self.db, actor_id, COOLDOWN_MINUTES)
                
                # Log alerts
                for event in fresh_events:
                    if event.get("id"):
                        await log_alert(self.db, actor_id, event["id"])
                
                logger.info(f"Alert sent to {actor_id}: {len(fresh_events)} events")
                return len(fresh_events)
            else:
                logger.warning(f"Failed to send alert to {actor_id}: {result.get('error')}")
                return 0
                
        except Exception as e:
            logger.error(f"Alert error for {actor_id}: {e}")
            return 0
    
    async def run_check(self):
        """Run single check cycle"""
        self.check_count += 1
        
        # Get active subscriptions
        cursor = self.db.geo_alert_subscriptions.find({"enabled": True})
        subscriptions = await cursor.to_list(1000)
        
        if not subscriptions:
            return
        
        total_alerts = 0
        for sub in subscriptions:
            alerts = await self.check_subscription(sub)
            total_alerts += alerts
        
        self.alert_count += total_alerts
        
        if total_alerts > 0:
            logger.info(f"Scheduler check #{self.check_count}: {total_alerts} alerts sent")
    
    async def run(self):
        """Run scheduler loop"""
        logger.info("Geo Alert Scheduler started")
        self.running = True
        
        while self.running:
            try:
                await self.run_check()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
    
    def stop(self):
        """Stop scheduler"""
        self.running = False
        logger.info(f"Geo Alert Scheduler stopped. Total: {self.check_count} checks, {self.alert_count} alerts")


# Global instance
_scheduler_instance: Optional[GeoAlertScheduler] = None


def get_scheduler(db) -> GeoAlertScheduler:
    """Get or create scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = GeoAlertScheduler(db)
    return _scheduler_instance


async def start_scheduler(db):
    """Start scheduler in background"""
    scheduler = get_scheduler(db)
    asyncio.create_task(scheduler.run())
    return scheduler
