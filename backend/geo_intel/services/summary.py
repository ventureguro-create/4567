"""
Geo AI Summary Service
Generates human-readable summaries using LLM
"""
import os
import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

logger = logging.getLogger(__name__)


async def generate_geo_summary_llm(stats_data: Dict) -> str:
    """
    Generate Ukrainian summary using LLM.
    """
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        from dotenv import load_dotenv
        load_dotenv()
        
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            logger.warning("EMERGENT_LLM_KEY not set, using fallback summary")
            return generate_fallback_summary(stats_data)
        
        # Prepare context
        context = json.dumps(stats_data, ensure_ascii=False, default=str, indent=2)
        
        system_message = """Ти — аналітик геопросторових даних. 
Твоє завдання — написати короткий, зрозумілий summary українською мовою.

Правила:
- Максимум 3-4 речення
- Конкретні факти, без води
- Вказуй найактивніші місця та години
- Якщо є аномалії — вкажи
- Мова: українська"""

        user_prompt = f"""Проаналізуй статистику geo-подій та напиши короткий summary:

{context}

Напиши summary українською (3-4 речення)."""

        chat = LlmChat(
            api_key=api_key,
            session_id=f"geo_summary_{datetime.now().timestamp()}",
            system_message=system_message
        ).with_model("openai", "gpt-4o")
        
        response = await chat.send_message(UserMessage(text=user_prompt))
        
        return response.strip() if response else generate_fallback_summary(stats_data)
        
    except Exception as e:
        logger.error(f"LLM summary error: {e}")
        return generate_fallback_summary(stats_data)


def generate_fallback_summary(stats_data: Dict) -> str:
    """
    Generate summary without LLM (fallback).
    """
    parts = []
    
    # Total events
    total = stats_data.get("totalEvents", 0)
    if total > 0:
        parts.append(f"За останній період зафіксовано {total} подій")
    
    # Top places
    top_places = stats_data.get("topPlaces", [])
    if top_places:
        top = top_places[0]
        parts.append(f"Найактивніше місце: {top.get('title', 'невідомо')} ({top.get('count', 0)} подій)")
    
    # Peak hours
    peak_hours = stats_data.get("peakHours", [])
    if peak_hours:
        hours_str = ", ".join([f"{h}:00" for h in peak_hours[:3]])
        parts.append(f"Пік активності: {hours_str}")
    
    # Event types
    virus_count = 0
    trash_count = 0
    for et in stats_data.get("eventTypes", []):
        if et.get("type") == "virus":
            virus_count = et.get("count", 0)
        elif et.get("type") == "trash":
            trash_count = et.get("count", 0)
    
    if virus_count > 0 or trash_count > 0:
        parts.append(f"Типи: 🦠 вірус ({virus_count}), 🗑️ сміття ({trash_count})")
    
    return ". ".join(parts) + "." if parts else "Недостатньо даних для аналізу."


async def get_summary_data(db, days: int = 7) -> Dict:
    """
    Collect all data needed for summary generation.
    """
    from .stats import get_full_stats
    from .predictor import predict_hotspots
    
    # Get stats
    stats = await get_full_stats(db, days=days)
    
    # Get predictions
    predictions = await predict_hotspots(db, days=30, limit=5)
    
    # Count by type
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    pipeline = [
        {"$match": {"createdAt": {"$gte": since}}},
        {"$group": {"_id": "$eventType", "count": {"$sum": 1}}}
    ]
    
    event_types = []
    async for doc in db.tg_geo_events.aggregate(pipeline):
        event_types.append({"type": doc["_id"], "count": doc["count"]})
    
    total_events = await db.tg_geo_events.count_documents({"createdAt": {"$gte": since}})
    
    return {
        "totalEvents": total_events,
        "days": days,
        "topPlaces": stats.get("topPlaces", [])[:5],
        "peakHours": stats.get("peakHours", []),
        "peakDays": stats.get("peakDays", []),
        "eventTypes": event_types,
        "predictions": predictions.get("predictions", [])[:3]
    }


async def generate_summary(db, days: int = 7, use_llm: bool = True) -> Dict:
    """
    Generate complete summary response.
    """
    # Collect data
    data = await get_summary_data(db, days=days)
    
    # Generate text
    if use_llm:
        summary_text = await generate_geo_summary_llm(data)
    else:
        summary_text = generate_fallback_summary(data)
    
    return {
        "ok": True,
        "summary": summary_text,
        "data": data,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "usedLLM": use_llm
    }
