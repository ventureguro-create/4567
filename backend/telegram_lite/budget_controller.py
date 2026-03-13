"""
Budget Controller - контроль MTProto запросов
Защита от flood ban через лимиты: minute/hour/day
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import os


# Лимиты по умолчанию
DEFAULT_LIMITS = {
    "minute": int(os.environ.get("TG_BUDGET_PER_MIN", 60)),
    "hour": int(os.environ.get("TG_BUDGET_PER_HOUR", 1000)),
    "day": int(os.environ.get("TG_BUDGET_PER_DAY", 15000)),
}

# Длительность окон в секундах
WINDOW_DURATION = {
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


async def init_budgets(db):
    """Инициализировать бюджеты если их нет"""
    now = datetime.now(timezone.utc)
    
    for window_id, limit in DEFAULT_LIMITS.items():
        await db.tg_mtproto_budget.update_one(
            {"_id": window_id},
            {
                "$setOnInsert": {
                    "_id": window_id,
                    "windowStart": now,
                    "used": 0,
                    "limit": limit,
                }
            },
            upsert=True
        )


def window_reset_needed(window_id: str, window_start: datetime) -> bool:
    """Проверить нужен ли сброс окна"""
    if not window_start:
        return True
    
    now = datetime.now(timezone.utc)
    
    # Ensure window_start is timezone-aware
    if isinstance(window_start, str):
        window_start = datetime.fromisoformat(window_start.replace('Z', '+00:00'))
    
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    
    elapsed = (now - window_start).total_seconds()
    return elapsed >= WINDOW_DURATION.get(window_id, 60)


async def budget_consume(db, cost: int = 1) -> Dict[str, Any]:
    """
    Попытаться потребить бюджет.
    Возвращает ok=True если можно продолжать, ok=False если лимит превышен.
    """
    windows = ["minute", "hour", "day"]
    
    for window_id in windows:
        doc = await db.tg_mtproto_budget.find_one({"_id": window_id})
        
        if not doc:
            # Инициализируем если нет
            await init_budgets(db)
            doc = await db.tg_mtproto_budget.find_one({"_id": window_id})
        
        if not doc:
            continue
        
        # Сброс окна если нужно
        if window_reset_needed(window_id, doc.get("windowStart")):
            await db.tg_mtproto_budget.update_one(
                {"_id": window_id},
                {"$set": {"windowStart": datetime.now(timezone.utc), "used": 0}}
            )
            doc = await db.tg_mtproto_budget.find_one({"_id": window_id})
        
        # Проверка лимита
        current_used = doc.get("used", 0)
        limit = doc.get("limit", DEFAULT_LIMITS.get(window_id, 100))
        
        if (current_used + cost) > limit:
            return {
                "ok": False,
                "reason": "BUDGET_EXCEEDED",
                "window": window_id,
                "used": current_used,
                "limit": limit,
                "resetIn": WINDOW_DURATION[window_id] - int((datetime.now(timezone.utc) - doc.get("windowStart", datetime.now(timezone.utc))).total_seconds()),
            }
    
    # Всё ок - потребляем атомарно
    for window_id in windows:
        await db.tg_mtproto_budget.update_one(
            {"_id": window_id},
            {"$inc": {"used": cost}}
        )
    
    # Логируем
    await db.tg_budget_log.insert_one({
        "cost": cost,
        "timestamp": datetime.now(timezone.utc),
    })
    
    return {"ok": True, "cost": cost}


async def get_budget_status(db) -> Dict[str, Any]:
    """Получить текущий статус бюджета"""
    result = {}
    now = datetime.now(timezone.utc)
    
    for window_id in ["minute", "hour", "day"]:
        doc = await db.tg_mtproto_budget.find_one({"_id": window_id})
        
        if doc:
            window_start = doc.get("windowStart")
            if isinstance(window_start, str):
                window_start = datetime.fromisoformat(window_start.replace('Z', '+00:00'))
            
            if window_start and window_start.tzinfo is None:
                window_start = window_start.replace(tzinfo=timezone.utc)
            
            elapsed = (now - window_start).total_seconds() if window_start else 0
            remaining_time = max(0, WINDOW_DURATION[window_id] - elapsed)
            
            result[window_id] = {
                "used": doc.get("used", 0),
                "limit": doc.get("limit", DEFAULT_LIMITS[window_id]),
                "remaining": doc.get("limit", DEFAULT_LIMITS[window_id]) - doc.get("used", 0),
                "resetInSeconds": int(remaining_time),
            }
        else:
            result[window_id] = {
                "used": 0,
                "limit": DEFAULT_LIMITS[window_id],
                "remaining": DEFAULT_LIMITS[window_id],
                "resetInSeconds": 0,
            }
    
    return result


async def record_flood_wait(db, seconds: int, username: str = None, method: str = None):
    """Записать flood wait событие"""
    await db.tg_flood_events.insert_one({
        "seconds": seconds,
        "username": username,
        "method": method,
        "timestamp": datetime.now(timezone.utc),
    })
    
    # Если flood > 60 секунд - входим в cooldown
    if seconds > 60:
        cooldown_until = datetime.now(timezone.utc) + timedelta(seconds=seconds + 30)
        await db.tg_runtime_state.update_one(
            {"_id": "ingestion_cooldown"},
            {
                "$set": {
                    "until": cooldown_until,
                    "reason": f"FLOOD_WAIT_{seconds}s",
                    "activatedAt": datetime.now(timezone.utc),
                }
            },
            upsert=True
        )


async def is_cooldown_active(db) -> Dict[str, Any]:
    """Проверить активен ли cooldown после flood"""
    doc = await db.tg_runtime_state.find_one({"_id": "ingestion_cooldown"})
    
    if not doc:
        return {"active": False}
    
    until = doc.get("until")
    if isinstance(until, str):
        until = datetime.fromisoformat(until.replace('Z', '+00:00'))
    
    if until and until > datetime.now(timezone.utc):
        return {
            "active": True,
            "until": until.isoformat(),
            "reason": doc.get("reason"),
            "remainingSeconds": int((until - datetime.now(timezone.utc)).total_seconds()),
        }
    
    return {"active": False}
