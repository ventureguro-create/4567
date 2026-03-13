"""
Geo Admin - Users Service
User management and analytics
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def get_users(
    db,
    page: int = 1,
    limit: int = 50,
    radar_enabled: Optional[bool] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Get list of bot users"""
    try:
        query = {}
        
        if radar_enabled is not None:
            query["radarEnabled"] = radar_enabled
        
        if search:
            query["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"actorId": {"$regex": search, "$options": "i"}}
            ]
        
        skip = (page - 1) * limit
        total = await db.geo_bot_users.count_documents(query)
        
        users = await db.geo_bot_users.find(
            query,
            {"_id": 0}
        ).sort("updatedAt", -1).skip(skip).limit(limit).to_list(limit)
        
        # Enrich with alert counts
        for user in users:
            actor_id = user.get("actorId")
            if actor_id:
                user["alertsReceived"] = await db.geo_alert_log.count_documents({
                    "actorId": actor_id
                })
                user["reportsSubmitted"] = await db.geo_user_reports.count_documents({
                    "actorId": actor_id
                })
        
        return {
            "ok": True,
            "items": users,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0)
        }
    except Exception as e:
        logger.error(f"Get users error: {e}")
        return {"ok": False, "error": str(e)}


async def get_user_details(db, actor_id: str) -> Dict[str, Any]:
    """Get detailed user information"""
    try:
        user = await db.geo_bot_users.find_one(
            {"actorId": actor_id},
            {"_id": 0}
        )
        
        if not user:
            return {"ok": False, "error": "User not found"}
        
        # Get user's alert history
        alerts = await db.geo_alert_log.find(
            {"actorId": actor_id},
            {"_id": 0}
        ).sort("sentAt", -1).limit(20).to_list(20)
        
        # Get user's reports
        reports = await db.geo_user_reports.find(
            {"actorId": actor_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(20).to_list(20)
        
        # Get settings
        settings = await db.geo_bot_settings.find_one(
            {"actorId": actor_id},
            {"_id": 0}
        )
        
        return {
            "ok": True,
            "user": user,
            "alerts": alerts,
            "reports": reports,
            "settings": settings
        }
    except Exception as e:
        logger.error(f"User details error: {e}")
        return {"ok": False, "error": str(e)}


async def get_user_analytics(db) -> Dict[str, Any]:
    """Get user analytics and trends"""
    try:
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)
        
        total = await db.geo_bot_users.count_documents({})
        radar_enabled = await db.geo_bot_users.count_documents({"radarEnabled": True})
        with_location = await db.geo_bot_users.count_documents({"lastLat": {"$ne": None}})
        
        # Active users (updated in last 7 days)
        active_7d = await db.geo_bot_users.count_documents({
            "updatedAt": {"$gte": last_7d}
        })
        
        # Active users (updated in last 30 days)
        active_30d = await db.geo_bot_users.count_documents({
            "updatedAt": {"$gte": last_30d}
        })
        
        # New users today
        new_today = await db.geo_bot_users.count_documents({
            "createdAt": {"$gte": today}
        })
        
        return {
            "ok": True,
            "total": total,
            "radarEnabled": radar_enabled,
            "withLocation": with_location,
            "active7d": active_7d,
            "active30d": active_30d,
            "newToday": new_today,
            "radarRate": round(radar_enabled / total * 100, 1) if total > 0 else 0,
            "locationRate": round(with_location / total * 100, 1) if total > 0 else 0
        }
    except Exception as e:
        logger.error(f"User analytics error: {e}")
        return {"ok": False, "error": str(e)}
