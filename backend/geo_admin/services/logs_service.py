"""
Geo Admin - Logs Service
Audit logs and system logging
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def log_admin_action(
    db,
    action: str,
    details: Dict[str, Any],
    admin_id: str = "system"
) -> Dict[str, Any]:
    """Log admin action for audit"""
    try:
        doc = {
            "action": action,
            "details": details,
            "adminId": admin_id,
            "createdAt": datetime.now(timezone.utc)
        }
        
        await db.geo_admin_logs.insert_one(doc)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Log action error: {e}")
        return {"ok": False, "error": str(e)}


async def get_admin_logs(
    db,
    page: int = 1,
    limit: int = 50,
    action_type: Optional[str] = None,
    days: int = 7
) -> Dict[str, Any]:
    """Get admin action logs"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = {"createdAt": {"$gte": cutoff}}
        
        if action_type:
            query["action"] = action_type
        
        skip = (page - 1) * limit
        total = await db.geo_admin_logs.count_documents(query)
        
        logs = await db.geo_admin_logs.find(
            query,
            {"_id": 0}
        ).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        
        return {
            "ok": True,
            "items": logs,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0)
        }
    except Exception as e:
        logger.error(f"Get admin logs error: {e}")
        return {"ok": False, "error": str(e)}


async def get_parsing_logs(
    db,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    days: int = 3
) -> Dict[str, Any]:
    """Get parsing job logs"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = {"createdAt": {"$gte": cutoff}}
        
        if status:
            query["status"] = status
        
        skip = (page - 1) * limit
        total = await db.geo_parsing_logs.count_documents(query)
        
        logs = await db.geo_parsing_logs.find(
            query,
            {"_id": 0}
        ).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        
        return {
            "ok": True,
            "items": logs,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0)
        }
    except Exception as e:
        logger.error(f"Get parsing logs error: {e}")
        return {"ok": False, "error": str(e)}


async def get_delivery_logs(
    db,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    days: int = 3
) -> Dict[str, Any]:
    """Get delivery logs"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        query = {"createdAt": {"$gte": cutoff}}
        
        if status:
            query["status"] = status
        
        skip = (page - 1) * limit
        total = await db.tg_delivery_outbox.count_documents(query)
        
        logs = await db.tg_delivery_outbox.find(
            query,
            {"_id": 0}
        ).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        
        return {
            "ok": True,
            "items": logs,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0)
        }
    except Exception as e:
        logger.error(f"Get delivery logs error: {e}")
        return {"ok": False, "error": str(e)}


async def get_error_summary(db, days: int = 7) -> Dict[str, Any]:
    """Get error summary across all logs"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Delivery errors
        delivery_failed = await db.tg_delivery_outbox.count_documents({
            "status": "FAILED",
            "createdAt": {"$gte": cutoff}
        })
        
        # Parsing errors
        parsing_failed = await db.geo_parsing_logs.count_documents({
            "status": "error",
            "createdAt": {"$gte": cutoff}
        })
        
        # Alert errors
        alert_failed = await db.geo_alert_log.count_documents({
            "status": "FAILED",
            "createdAt": {"$gte": cutoff}
        })
        
        return {
            "ok": True,
            "deliveryErrors": delivery_failed,
            "parsingErrors": parsing_failed,
            "alertErrors": alert_failed,
            "total": delivery_failed + parsing_failed + alert_failed
        }
    except Exception as e:
        logger.error(f"Error summary error: {e}")
        return {"ok": False, "error": str(e)}
