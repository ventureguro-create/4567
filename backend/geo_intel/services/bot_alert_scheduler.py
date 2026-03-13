"""
Bot Alert Scheduler - Check proximity and send alerts to active users
"""
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional, Callable, Awaitable, Any

from .bot_user_service import BotUserService
from .bot_settings_service import BotSettingsService
from .bot_location_service import BotLocationService
from .bot_alert_service import BotAlertService
from .proximity import get_nearby_events

logger = logging.getLogger(__name__)


class BotAlertScheduler:
    """Scheduler that checks proximity for all active users and sends alerts"""
    
    def __init__(
        self, 
        db, 
        send_message_func: Optional[Callable[..., Awaitable[Any]]] = None,
        interval_seconds: int = 60
    ):
        self.db = db
        self.send_message = send_message_func
        self.interval = interval_seconds
        self.running = False
        
        # Services
        self.user_service = BotUserService(db)
        self.settings_service = BotSettingsService(db)
        self.location_service = BotLocationService(db)
        self.alert_service = BotAlertService(db)
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            return
        
        self.running = True
        asyncio.create_task(self._loop())
        logger.info("Bot Alert Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        logger.info("Bot Alert Scheduler stopped")
    
    async def _loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                await self._check_all_users()
            except Exception as e:
                logger.error(f"Alert scheduler error: {e}", exc_info=True)
            
            await asyncio.sleep(self.interval)
    
    async def _check_all_users(self):
        """Check proximity for all users with radar enabled"""
        
        # Get all users with radar enabled
        settings_list = await self.settings_service.get_users_with_radar_enabled()
        
        if not settings_list:
            return
        
        alerts_sent = 0
        
        for settings in settings_list:
            actor_id = settings.get("actorId")
            if not actor_id:
                continue
            
            try:
                sent = await self._check_user_proximity(actor_id, settings)
                if sent:
                    alerts_sent += 1
            except Exception as e:
                logger.error(f"Error checking user {actor_id}: {e}")
        
        if alerts_sent > 0:
            logger.info(f"Sent {alerts_sent} proximity alerts")
    
    async def _check_user_proximity(
        self, 
        actor_id: str, 
        settings: dict
    ) -> bool:
        """Check proximity for single user and send alert if needed"""
        
        # Get location
        location = await self.location_service.get_location(actor_id)
        if not location:
            return False
        
        # Check if location is fresh enough (within 24 hours)
        if not await self.location_service.has_recent_location(actor_id, max_age_minutes=1440):
            return False
        
        lat = location["lat"]
        lng = location["lng"]
        radius = settings.get("radius", 1000)
        event_types = settings.get("eventTypes", [])
        sensitivity = settings.get("sensitivity", "medium")
        quiet_hours = settings.get("quietHours", {})
        
        # Check quiet hours
        if self.alert_service.is_quiet_hours(quiet_hours):
            return False
        
        # Get nearby events
        result = await get_nearby_events(
            self.db,
            lat=lat,
            lng=lng,
            radius_m=radius,
            days=1
        )
        
        events = result.get("items", [])
        
        if not events:
            return False
        
        # Filter by event types
        if event_types:
            events = [e for e in events if e.get("eventType") in event_types]
        
        if not events:
            return False
        
        # Filter by sensitivity
        events = self._filter_by_sensitivity(events, sensitivity)
        
        if not events:
            return False
        
        # Check cooldown for each event
        sendable_events = []
        for event in events:
            event_id = str(event.get("id", event.get("_id", "")))
            event_type = event.get("eventType", "unknown")
            
            can_send = await self.alert_service.can_send_alert(
                actor_id=actor_id,
                event_id=event_id,
                event_type=event_type
            )
            
            if can_send:
                sendable_events.append(event)
        
        if not sendable_events:
            return False
        
        # Send alert
        if self.send_message:
            chat_id = int(actor_id.replace("tg_", ""))
            
            text = self.alert_service.format_proximity_alert(
                sendable_events, lat, lng, radius
            )
            
            try:
                await self.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )
                
                # Log alert
                first_event = sendable_events[0]
                await self.alert_service.log_alert(
                    actor_id=actor_id,
                    event_id=str(first_event.get("id", first_event.get("_id", ""))),
                    event_type=first_event.get("eventType", "unknown"),
                    alert_type="PROXIMITY"
                )
                
                logger.info(f"Sent proximity alert to {actor_id}: {len(sendable_events)} events")
                return True
                
            except Exception as e:
                logger.error(f"Failed to send alert to {actor_id}: {e}")
                return False
        
        return False
    
    def _filter_by_sensitivity(self, events: list, sensitivity: str) -> list:
        """Filter events by sensitivity level"""
        if sensitivity == "high":
            # All events
            return events
        
        if sensitivity == "medium":
            # Confirmed + active (score >= 0.4)
            return [e for e in events if (e.get("score") or e.get("confidence") or 0) >= 0.4]
        
        if sensitivity == "low":
            # Only confirmed (score >= 0.7)
            return [e for e in events if (e.get("score") or e.get("confidence") or 0) >= 0.7]
        
        return events
    
    async def run_once(self) -> dict:
        """Run single check (for manual trigger)"""
        try:
            await self._check_all_users()
            return {"ok": True, "message": "Check completed"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
