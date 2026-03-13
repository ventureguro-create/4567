"""
Geo Admin - Analytics Service
System analytics and reporting
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def get_events_by_day(db, days: int = 30) -> Dict[str, Any]:
    """Get geo events grouped by day"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}
                    },
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        results = await db.tg_geo_events.aggregate(pipeline).to_list(100)
        
        return {
            "ok": True,
            "items": [{"date": r["_id"], "count": r["count"]} for r in results]
        }
    except Exception as e:
        logger.error(f"Events by day error: {e}")
        return {"ok": False, "error": str(e)}


async def get_top_event_types(db, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    """Get most common event types"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}}},
            {
                "$group": {
                    "_id": "$type",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        results = await db.tg_geo_events.aggregate(pipeline).to_list(limit)
        
        return {
            "ok": True,
            "items": [{"type": r["_id"], "count": r["count"]} for r in results]
        }
    except Exception as e:
        logger.error(f"Top event types error: {e}")
        return {"ok": False, "error": str(e)}


async def get_top_districts(db, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    """Get districts with most events"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}, "district": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$district",
                    "count": {"$sum": 1}
                }
            },
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        results = await db.tg_geo_events.aggregate(pipeline).to_list(limit)
        
        return {
            "ok": True,
            "items": [{"district": r["_id"], "count": r["count"]} for r in results]
        }
    except Exception as e:
        logger.error(f"Top districts error: {e}")
        return {"ok": False, "error": str(e)}


async def get_source_breakdown(db, days: int = 30) -> Dict[str, Any]:
    """Get events by source (telegram vs user reports)"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        telegram_events = await db.tg_geo_events.count_documents({
            "createdAt": {"$gte": cutoff},
            "sourceType": {"$in": ["telegram", "channel", None]}
        })
        
        user_reports = await db.geo_user_reports.count_documents({
            "createdAt": {"$gte": cutoff}
        })
        
        return {
            "ok": True,
            "telegramEvents": telegram_events,
            "userReports": user_reports,
            "total": telegram_events + user_reports
        }
    except Exception as e:
        logger.error(f"Source breakdown error: {e}")
        return {"ok": False, "error": str(e)}


async def get_alert_analytics(db, days: int = 30) -> Dict[str, Any]:
    """Get alert delivery analytics"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Total alerts
        total_sent = await db.geo_alert_log.count_documents({
            "sentAt": {"$gte": cutoff}
        })
        
        # By status
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        status_results = await db.geo_alert_log.aggregate(pipeline).to_list(10)
        status_map = {r["_id"]: r["count"] for r in status_results}
        
        # Unique users who received alerts
        unique_users = await db.geo_alert_log.distinct(
            "actorId",
            {"sentAt": {"$gte": cutoff}}
        )
        
        return {
            "ok": True,
            "totalSent": total_sent,
            "byStatus": status_map,
            "uniqueRecipients": len(unique_users),
            "avgPerUser": round(total_sent / len(unique_users), 1) if unique_users else 0
        }
    except Exception as e:
        logger.error(f"Alert analytics error: {e}")
        return {"ok": False, "error": str(e)}


async def get_channel_performance(db, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    """Get channel performance ranking"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        pipeline = [
            {"$match": {"createdAt": {"$gte": cutoff}, "source": {"$ne": None}}},
            {
                "$group": {
                    "_id": "$source",
                    "eventsCount": {"$sum": 1}
                }
            },
            {"$sort": {"eventsCount": -1}},
            {"$limit": limit}
        ]
        
        results = await db.tg_geo_events.aggregate(pipeline).to_list(limit)
        
        # Enrich with channel info
        items = []
        for r in results:
            channel = await db.geo_channels.find_one(
                {"username": r["_id"]},
                {"_id": 0, "title": 1, "enabled": 1}
            )
            items.append({
                "username": r["_id"],
                "eventsCount": r["eventsCount"],
                "title": channel.get("title") if channel else r["_id"],
                "enabled": channel.get("enabled", False) if channel else False
            })
        
        return {"ok": True, "items": items}
    except Exception as e:
        logger.error(f"Channel performance error: {e}")
        return {"ok": False, "error": str(e)}
