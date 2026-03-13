"""
Probability Engine
Calculates event probabilities based on historical patterns
"""
import re
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from .probability_repository import ProbabilityRepository

logger = logging.getLogger(__name__)


def make_place_key(title: str) -> str:
    """Create normalized key from title"""
    if not title:
        return "unknown"
    # Remove special chars, lowercase
    key = re.sub(r"[^a-zA-Z0-9а-яА-ЯіїєІЇЄ]+", "_", title.strip().lower())
    return key.strip("_")[:50]


class ProbabilityEngine:
    """Engine for computing event probabilities"""
    
    def __init__(self, repo: ProbabilityRepository):
        self.repo = repo
    
    async def rebuild(self) -> Dict:
        """Rebuild all probability records"""
        events = await self.repo.get_recent_events(30)
        
        if not events:
            logger.info("No events found for probability calculation")
            return {"ok": True, "processed": 0}
        
        # Group by place + eventType
        grouped = defaultdict(list)
        for e in events:
            title = e.get("title", "")
            event_type = e.get("eventType", "virus")
            key = (make_place_key(title), event_type)
            grouped[key].append(e)
        
        now = datetime.now(timezone.utc)
        weekday_now = now.weekday()  # 0=Monday
        hour_now = now.hour
        weekday_tomorrow = (weekday_now + 1) % 7
        
        processed = 0
        
        for (place_key, event_type), items in grouped.items():
            if not items or not place_key:
                continue
            
            # Get first item for location info
            first = items[0]
            title = first.get("title", place_key)
            
            # Extract coordinates
            loc = first.get("location", {})
            lat = loc.get("lat")
            lng = loc.get("lng")
            
            if lat is None or lng is None:
                continue
            
            # Count events
            count30d = len(items)
            count7d = sum(
                1 for i in items
                if i.get("createdAt") and (now - i["createdAt"].replace(tzinfo=timezone.utc) if i["createdAt"].tzinfo is None else now - i["createdAt"]).days < 7
            )
            
            # Analyze patterns
            hour_counts = defaultdict(int)
            weekday_counts = defaultdict(int)
            unique_days = set()
            
            for i in items:
                created = i.get("createdAt")
                if created:
                    # Handle naive datetime
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    hour_counts[created.hour] += 1
                    weekday_counts[created.weekday()] += 1
                    unique_days.add(created.date())
            
            # Top hours and weekdays
            top_hours = [h for h, _ in sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
            top_weekdays = [d for d, _ in sorted(weekday_counts.items(), key=lambda x: x[1], reverse=True)[:3]]
            
            # Calculate scores
            freq_score = min(count30d / 20, 1.0)
            hour_score_now = 1.0 if hour_now in top_hours else 0.3
            weekday_score_now = 1.0 if weekday_now in top_weekdays else 0.4
            weekday_score_tomorrow = 1.0 if weekday_tomorrow in top_weekdays else 0.4
            repeatability_score = min(len(unique_days) / 30, 1.0)
            
            # Calculate probabilities
            probability_now = round(
                freq_score * 0.4 +
                hour_score_now * 0.25 +
                weekday_score_now * 0.2 +
                repeatability_score * 0.15,
                2
            )
            
            probability_tomorrow = round(
                freq_score * 0.4 +
                hour_score_now * 0.25 +
                weekday_score_tomorrow * 0.2 +
                repeatability_score * 0.15,
                2
            )
            
            doc = {
                "placeKey": place_key,
                "title": title,
                "lat": lat,
                "lng": lng,
                "eventType": event_type,
                "count7d": count7d,
                "count30d": count30d,
                "topHours": top_hours,
                "topWeekdays": top_weekdays,
                "repeatabilityScore": round(repeatability_score, 2),
                "probabilityNow": probability_now,
                "probabilityTomorrow": probability_tomorrow,
                "updatedAt": now
            }
            
            await self.repo.upsert_probability(doc)
            processed += 1
        
        logger.info(f"Probability engine processed {processed} places")
        return {"ok": True, "processed": processed}
