"""
Bot Status Service - Build status messages for users
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

EVENT_ICONS = {
    "virus": "🦠",
    "trash": "🗑",
    "rain": "🌧",
    "heavy_rain": "⛈"
}

MODE_LABELS = {
    "5m": "5 хв",
    "15m": "15 хв",
    "1h": "1 година",
    "1d": "1 день",
    "permanent": "Постійно",
    "none": "Не зберігається"
}


class BotStatusService:
    """Service for building user status information"""
    
    def __init__(self, db):
        self.db = db
    
    async def build_status(
        self,
        user: Dict[str, Any],
        settings: Dict[str, Any],
        location: Optional[Dict[str, Any]]
    ) -> str:
        """Build full status message"""
        actor_id = user.get("actorId")
        
        lines = ["📊 *Статус*", ""]
        
        # Radar status
        radar_on = settings.get("radarEnabled", False)
        radar_emoji = "🟢" if radar_on else "🔴"
        lines.append(f"Радар: {radar_emoji} {'увімкнено' if radar_on else 'вимкнено'}")
        
        # Geo Session info (NEW)
        if actor_id:
            session = await self.db.geo_sessions.find_one(
                {"userId": actor_id, "isActive": True},
                {"_id": 0, "expiresAt": 1, "mode": 1, "radius": 1}
            )
            
            if session:
                mode = session.get("mode", "15m")
                mode_label = MODE_LABELS.get(mode, mode)
                
                expires_at = session.get("expiresAt")
                if expires_at:
                    now = datetime.now(timezone.utc)
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    
                    remaining = expires_at - now
                    remaining_min = int(remaining.total_seconds() / 60)
                    
                    if remaining_min > 0:
                        if remaining_min < 60:
                            time_str = f"{remaining_min} хв"
                        else:
                            time_str = f"{remaining_min // 60} год {remaining_min % 60} хв"
                        lines.append(f"⏱ Сесія: залишилось {time_str}")
                    else:
                        lines.append("⏱ Сесія: завершена")
                
                lines.append(f"📍 Режим: {mode_label}")
            else:
                lines.append("⏱ Сесія: не активна")
        
        # Radius
        radius = settings.get("radius", 1000)
        lines.append(f"🎯 Радіус: {radius} м")
        
        # Event types
        types = settings.get("eventTypes", [])
        if types:
            type_str = ", ".join([EVENT_ICONS.get(t, t) for t in types])
            lines.append(f"🧩 Типи: {type_str}")
        
        # Privacy note
        lines.append("")
        lines.append("🔒 _Локація автоматично видаляється_")
        
        return "\n".join(lines)
    
    async def build_short_status(self, settings: Dict[str, Any]) -> str:
        """Build short status line"""
        radar_on = settings.get("radarEnabled", False)
        radius = settings.get("radius", 1000)
        types_count = len(settings.get("eventTypes", []))
        
        if radar_on:
            return f"📡 ON • {radius}м • {types_count} типів"
        else:
            return "📡 OFF"
    
    async def build_proximity_stats(
        self,
        actor_id: str,
        lat: float,
        lng: float,
        radius: int,
        hours: int = 24
    ) -> str:
        """Build proximity statistics"""
        from .proximity import get_nearby_events
        
        result = await get_nearby_events(
            self.db, 
            lat=lat, 
            lng=lng, 
            radius_m=radius, 
            days=1
        )
        
        events = result.get("items", [])
        count = len(events)
        
        if count == 0:
            return "✅ Поблизу немає активних сигналів"
        
        # Group by type
        by_type = {}
        for e in events:
            etype = e.get("eventType", "unknown")
            by_type[etype] = by_type.get(etype, 0) + 1
        
        lines = [f"⚠️ Знайдено {count} сигналів у радіусі {radius} м:", ""]
        
        for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            icon = EVENT_ICONS.get(etype, "•")
            lines.append(f"{icon} {etype}: {cnt}")
        
        return "\n".join(lines)
