"""
Bot Summary Service - Generate summaries for bot users
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

EVENT_ICONS = {
    "virus": "🦠",
    "trash": "🗑",
    "rain": "🌧",
    "heavy_rain": "⛈"
}


class BotSummaryService:
    """Service for generating summaries"""
    
    def __init__(self, db):
        self.db = db
    
    async def generate_summary(
        self,
        hours: int = 24,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        radius: int = 5000
    ) -> str:
        """Generate summary text for bot"""
        
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Get events
        query = {"createdAt": {"$gte": since}}
        events = await self.db.tg_geo_events.find(query).to_list(1000)
        
        if not events:
            return f"🧠 *Summary* (останні {hours} год)\n\nПодій не знайдено."
        
        # Count by type
        by_type = {}
        for e in events:
            etype = e.get("eventType", "unknown")
            by_type[etype] = by_type.get(etype, 0) + 1
        
        # Count by place
        by_place = {}
        for e in events:
            place = e.get("title", "Невідомо")
            by_place[place] = by_place.get(place, 0) + 1
        
        # Top places
        top_places = sorted(by_place.items(), key=lambda x: -x[1])[:5]
        
        # Build message
        lines = [
            f"🧠 *Summary* (останні {hours} год)",
            "",
            f"📊 Всього подій: {len(events)}",
            ""
        ]
        
        # By type
        lines.append("*За типом:*")
        for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
            icon = EVENT_ICONS.get(etype, "•")
            lines.append(f"{icon} {etype}: {cnt}")
        
        lines.append("")
        
        # Top places
        if top_places:
            lines.append("*Найактивніші місця:*")
            for i, (place, cnt) in enumerate(top_places, 1):
                lines.append(f"{i}. {place} ({cnt})")
        
        # Peak hours
        hours_dist = {}
        for e in events:
            created = e.get("createdAt")
            if created:
                hour = created.hour
                hours_dist[hour] = hours_dist.get(hour, 0) + 1
        
        if hours_dist:
            peak_hour = max(hours_dist.items(), key=lambda x: x[1])
            lines.append("")
            lines.append(f"⏰ Пік активності: {peak_hour[0]}:00")
        
        return "\n".join(lines)
    
    async def generate_user_summary(
        self,
        actor_id: str,
        lat: float,
        lng: float,
        radius: int = 2000,
        hours: int = 24
    ) -> str:
        """Generate personalized summary for user location"""
        from .proximity import get_nearby_events
        from ..utils.geo_distance import haversine_distance
        
        # Get nearby events
        result = await get_nearby_events(
            self.db,
            lat=lat,
            lng=lng,
            radius_m=radius * 2,  # Extended radius for summary
            days=1
        )
        
        events = result.get("items", [])
        
        if not events:
            return f"🧠 *Ваш Summary*\n\n✅ Поблизу немає активних сигналів у радіусі {radius * 2} м."
        
        # Group by distance
        close = [e for e in events if e.get("distance", 9999) <= radius]
        far = [e for e in events if e.get("distance", 9999) > radius]
        
        lines = [
            "🧠 *Ваш Summary*",
            "",
        ]
        
        if close:
            lines.append(f"⚠️ У вашому радіусі ({radius} м): {len(close)} сигналів")
            
            # By type
            by_type = {}
            for e in close:
                etype = e.get("eventType", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
            
            for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
                icon = EVENT_ICONS.get(etype, "•")
                lines.append(f"  {icon} {etype}: {cnt}")
        else:
            lines.append(f"✅ У вашому радіусі ({radius} м) чисто")
        
        if far:
            lines.append("")
            lines.append(f"📍 Далі ({radius}-{radius*2} м): {len(far)} сигналів")
        
        return "\n".join(lines)
    
    async def should_send_daily_digest(self, actor_id: str) -> bool:
        """Check if we should send daily digest"""
        # Check last digest
        last = await self.db.geo_bot_alert_log.find_one(
            {"actorId": actor_id, "alertType": "DIGEST"},
            sort=[("sentAt", -1)]
        )
        
        if not last:
            return True
        
        sent_at = last.get("sentAt")
        if not sent_at:
            return True
        
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        
        age_hours = (datetime.now(timezone.utc) - sent_at).total_seconds() / 3600
        return age_hours >= 20  # At least 20 hours between digests
