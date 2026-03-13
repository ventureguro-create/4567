"""
Snapshot Validator - проверка целостности данных
Защита от мусора в UI через обнаружение аномалий
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional


class AnomalyType:
    NULL_FIELDS = "NULL_FIELDS"
    REACH_SPIKE = "REACH_SPIKE"
    MEMBERS_SPIKE = "MEMBERS_SPIKE"
    UTILITY_SPIKE = "UTILITY_SPIKE"
    DATE_GAP = "DATE_GAP"
    ARTIFICIAL_GROWTH = "ARTIFICIAL_GROWTH"


class Severity:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


async def validate_snapshots(db, days: int = 30) -> Dict[str, Any]:
    """
    Валидация snapshots за последние N дней.
    Ищет аномалии: NULL поля, резкие скачки, подозрительный рост.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    
    cursor = db.tg_score_snapshots.find(
        {"date": {"$gte": since}}
    ).sort([("username", 1), ("date", 1)])
    
    snapshots = await cursor.to_list(10000)
    
    anomalies = []
    prev = None
    
    for s in snapshots:
        username = s.get("username")
        
        # 1. NULL fields check
        if s.get("utility") is None or s.get("engagement") is None:
            anomalies.append({
                "username": username,
                "date": s.get("date"),
                "type": AnomalyType.NULL_FIELDS,
                "severity": Severity.MEDIUM,
                "meta": {
                    "utility": s.get("utility"),
                    "engagement": s.get("engagement"),
                },
            })
        
        # 2. Per-channel sequential checks
        if prev and prev.get("username") == username:
            prev_reach = prev.get("avgReach") or prev.get("engagement", 0) * 1000
            curr_reach = s.get("avgReach") or s.get("engagement", 0) * 1000
            
            # Reach spike (5x+)
            if prev_reach > 0 and curr_reach > 0:
                ratio = curr_reach / prev_reach
                if ratio >= 5:
                    anomalies.append({
                        "username": username,
                        "date": s.get("date"),
                        "type": AnomalyType.REACH_SPIKE,
                        "severity": Severity.HIGH,
                        "meta": {
                            "prevReach": prev_reach,
                            "currReach": curr_reach,
                            "ratio": round(ratio, 2),
                        },
                    })
            
            # Utility spike (jump > 30 points in one snapshot)
            prev_utility = prev.get("utility", 0)
            curr_utility = s.get("utility", 0)
            if prev_utility and curr_utility:
                utility_jump = abs(curr_utility - prev_utility)
                if utility_jump > 30:
                    anomalies.append({
                        "username": username,
                        "date": s.get("date"),
                        "type": AnomalyType.UTILITY_SPIKE,
                        "severity": Severity.MEDIUM,
                        "meta": {
                            "prevUtility": prev_utility,
                            "currUtility": curr_utility,
                            "jump": utility_jump,
                        },
                    })
        
        prev = s
    
    # Сохраняем аномалии в базу
    if anomalies:
        now = datetime.now(timezone.utc)
        for a in anomalies:
            a["createdAt"] = now
            await db.tg_snapshot_anomalies.update_one(
                {
                    "username": a["username"],
                    "date": a["date"],
                    "type": a["type"],
                },
                {"$set": a},
                upsert=True
            )
    
    return {
        "ok": True,
        "days": days,
        "snapshotsChecked": len(snapshots),
        "anomaliesFound": len(anomalies),
        "anomalies": anomalies[:50],  # Первые 50 для ответа
    }


async def detect_artificial_growth(db, username: str) -> Dict[str, Any]:
    """
    Детектор фейкового роста.
    Если growth7 > 40% но engagementRate падает - подозрительно.
    """
    # Последние 2 snapshot для канала
    snapshots = await db.tg_score_snapshots.find(
        {"username": username}
    ).sort("date", -1).limit(2).to_list(2)
    
    if len(snapshots) < 2:
        return {"ok": True, "suspicious": False, "reason": "NOT_ENOUGH_DATA"}
    
    current = snapshots[0]
    previous = snapshots[1]
    
    growth7 = current.get("growth7", 0)
    curr_engagement = current.get("engagement", 0)
    prev_engagement = previous.get("engagement", 0)
    
    suspicious = False
    reasons = []
    
    # Правило: growth > 40% но engagement падает
    if growth7 > 40:
        if prev_engagement > 0 and curr_engagement < prev_engagement * 0.8:
            suspicious = True
            reasons.append("HIGH_GROWTH_LOW_ENGAGEMENT")
    
    # Правило: резкий рост members но views не растут
    state = await db.tg_channel_states.find_one({"username": username})
    if state:
        members = state.get("participantsCount", 0)
        avg_reach = current.get("avgReach") or (curr_engagement * members) if members else 0
        
        if members > 10000 and avg_reach > 0:
            reach_ratio = avg_reach / members
            if reach_ratio < 0.01 and growth7 > 20:
                suspicious = True
                reasons.append("LOW_REACH_RATIO_HIGH_GROWTH")
    
    if suspicious:
        # Сохраняем аномалию
        await db.tg_snapshot_anomalies.insert_one({
            "username": username,
            "date": datetime.now(timezone.utc),
            "type": AnomalyType.ARTIFICIAL_GROWTH,
            "severity": Severity.HIGH,
            "meta": {
                "growth7": growth7,
                "currEngagement": curr_engagement,
                "prevEngagement": prev_engagement,
                "reasons": reasons,
            },
            "createdAt": datetime.now(timezone.utc),
        })
        
        # Помечаем канал
        await db.tg_channel_states.update_one(
            {"username": username},
            {"$set": {"flags.artificialGrowthSuspected": True, "flags.flaggedAt": datetime.now(timezone.utc)}}
        )
    
    return {
        "ok": True,
        "username": username,
        "suspicious": suspicious,
        "reasons": reasons,
        "growth7": growth7,
        "engagementChange": round((curr_engagement - prev_engagement) / max(0.001, prev_engagement) * 100, 1) if prev_engagement else 0,
    }


async def get_anomaly_summary(db) -> Dict[str, Any]:
    """Сводка по аномалиям"""
    # По типам
    by_type = await db.tg_snapshot_anomalies.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]).to_list(20)
    
    # По severity
    by_severity = await db.tg_snapshot_anomalies.aggregate([
        {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
    ]).to_list(10)
    
    # Последние 10
    recent = await db.tg_snapshot_anomalies.find().sort("createdAt", -1).limit(10).to_list(10)
    
    return {
        "ok": True,
        "byType": {x["_id"]: x["count"] for x in by_type},
        "bySeverity": {x["_id"]: x["count"] for x in by_severity},
        "recent": [
            {
                "username": r.get("username"),
                "type": r.get("type"),
                "severity": r.get("severity"),
                "createdAt": r.get("createdAt").isoformat() if r.get("createdAt") else None,
            }
            for r in recent
        ],
    }


async def mark_channel_inconsistent(db, username: str, reason: str):
    """Пометить канал как inconsistent - не показывать в UI"""
    await db.tg_channel_states.update_one(
        {"username": username},
        {
            "$set": {
                "dataIntegrity": {
                    "status": "INCONSISTENT",
                    "reason": reason,
                    "flaggedAt": datetime.now(timezone.utc),
                }
            }
        }
    )
