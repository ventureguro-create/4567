"""
Bot Alert Service - Manage proximity alerts with anti-spam
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Cooldown rules per event type (minutes)
ALERT_COOLDOWN = {
    "virus": 30,
    "trash": 60,
    "rain": 30,
    "heavy_rain": 20,
    "default": 30
}

# Event icons
EVENT_ICONS = {
    "virus": "🦠",
    "trash": "🗑",
    "rain": "🌧",
    "heavy_rain": "⛈"
}


class BotAlertService:
    """Service for managing alerts with anti-spam logic"""
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_bot_alert_log
    
    async def can_send_alert(
        self, 
        actor_id: str, 
        event_id: str,
        event_type: str
    ) -> bool:
        """Check if we can send this alert (cooldown + duplicate check)"""
        
        # Check for duplicate (same event)
        duplicate = await self.collection.find_one({
            "actorId": actor_id,
            "eventId": event_id
        })
        
        if duplicate:
            return False
        
        # Check cooldown for event type
        cooldown = ALERT_COOLDOWN.get(event_type, ALERT_COOLDOWN["default"])
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown)
        
        recent = await self.collection.find_one({
            "actorId": actor_id,
            "eventType": event_type,
            "sentAt": {"$gte": cutoff}
        })
        
        return recent is None
    
    async def log_alert(
        self,
        actor_id: str,
        event_id: str,
        event_type: str,
        alert_type: str = "PROXIMITY"
    ):
        """Log sent alert"""
        doc = {
            "actorId": actor_id,
            "eventId": event_id,
            "eventType": event_type,
            "alertType": alert_type,
            "sentAt": datetime.now(timezone.utc)
        }
        await self.collection.insert_one(doc)
        logger.info(f"Logged alert: {actor_id} <- {event_type}:{event_id}")
    
    async def get_recent_alerts(
        self, 
        actor_id: str, 
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get alerts sent to user in last N hours"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        cursor = self.collection.find(
            {"actorId": actor_id, "sentAt": {"$gte": cutoff}},
            {"_id": 0}
        ).sort("sentAt", -1)
        return [doc async for doc in cursor]
    
    async def cleanup_old_logs(self, days: int = 7) -> int:
        """Remove old alert logs"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = await self.collection.delete_many({"sentAt": {"$lt": cutoff}})
        return result.deleted_count
    
    def format_proximity_alert(
        self,
        events: List[Dict[str, Any]],
        user_lat: float,
        user_lng: float,
        radius: int
    ) -> str:
        """Format proximity alert message"""
        if not events:
            return ""
        
        count = len(events)
        nearest = events[0]
        
        icon = EVENT_ICONS.get(nearest.get("eventType", ""), "⚠️")
        
        # Calculate age
        created = nearest.get("createdAt")
        if created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age_minutes = int((datetime.now(timezone.utc) - created).total_seconds() / 60)
            
            if age_minutes < 60:
                age_str = f"{age_minutes} хв тому"
            else:
                age_str = f"{age_minutes // 60} год тому"
        else:
            age_str = "невідомо"
        
        # Build message
        lines = [
            "⚠️ *Увага*",
            "",
            f"У радіусі {radius} м знайдено {count} сигнал{'и' if count > 1 else ''}.",
            "",
            "Найближчий:",
            f"{icon} *{nearest.get('title', 'Невідомо')}*",
            f"📍 {nearest.get('distance', '?')} м від вас",
            f"🕐 {age_str}",
        ]
        
        # Add confidence if available
        score = nearest.get("score") or nearest.get("confidence")
        if score:
            if score >= 0.7:
                lines.append("✅ Статус: підтверджено")
            elif score >= 0.4:
                lines.append("🔸 Статус: активний")
            else:
                lines.append("🔹 Статус: очікує")
        
        return "\n".join(lines)
    
    def format_cluster_alert(
        self,
        cluster: Dict[str, Any],
        user_lat: float,
        user_lng: float
    ) -> str:
        """Format cluster/zone alert message"""
        event_type = cluster.get("eventType", "")
        icon = EVENT_ICONS.get(event_type, "⚠️")
        
        lines = [
            "🔴 *Зона ризику*",
            "",
            f"{icon} Тип: {event_type}",
            f"📊 Рівень: {cluster.get('riskLevel', 'невідомо')}",
            f"📍 {cluster.get('distanceMeters', '?')} м від вас",
            f"🎯 Радіус зони: {cluster.get('radiusMeters', '?')} м",
            f"📈 Подій: {cluster.get('eventCount', '?')}",
        ]
        
        return "\n".join(lines)
    
    def is_quiet_hours(self, quiet_hours: Dict[str, Any]) -> bool:
        """Check if current time is within quiet hours"""
        if not quiet_hours or not quiet_hours.get("enabled"):
            return False
        
        now = datetime.now(timezone.utc)
        current_hour = now.hour
        
        from_hour = quiet_hours.get("from", 23)
        to_hour = quiet_hours.get("to", 7)
        
        # Handle overnight range (e.g., 23:00 to 07:00)
        if from_hour > to_hour:
            return current_hour >= from_hour or current_hour < to_hour
        else:
            return from_hour <= current_hour < to_hour
