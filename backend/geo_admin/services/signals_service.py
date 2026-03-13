"""
Geo Admin - Signals Service
CRUD operations for geo signals (events)
Admin moderation: confirm, dismiss, edit, create manual signals
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import secrets

logger = logging.getLogger(__name__)

# Event type options
EVENT_TYPES = [
    "military_movement",
    "explosion",
    "air_alert",
    "missile",
    "drone",
    "gunfire",
    "checkpoint",
    "accident",
    "fire",
    "protest",
    "emergency",
    "unknown"
]

# Signal statuses
SIGNAL_STATUSES = ["raw", "weak", "medium", "confirmed", "dismissed"]


async def get_signals(
    db,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    search: Optional[str] = None,
    hours: int = 24,
    sort_by: str = "createdAt",
    sort_dir: str = "desc"
) -> Dict[str, Any]:
    """Get list of signals with filtering and pagination"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        query = {"createdAt": {"$gte": cutoff}}
        
        if status:
            query["status"] = status
        
        if event_type:
            query["eventType"] = event_type
        
        if search:
            query["$or"] = [
                {"title": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
                {"source": {"$regex": search, "$options": "i"}},
                {"address": {"$regex": search, "$options": "i"}}
            ]
        
        skip = (page - 1) * limit
        total = await db.geo_signals.count_documents(query)
        
        sort_order = -1 if sort_dir == "desc" else 1
        
        signals = await db.geo_signals.find(
            query,
            {"_id": 0}
        ).sort(sort_by, sort_order).skip(skip).limit(limit).to_list(limit)
        
        # Enrich with reports count
        for signal in signals:
            signal_id = signal.get("signalId")
            if signal_id:
                reports_count = await db.geo_reports.count_documents({
                    "signalId": signal_id
                })
                signal["reportsCount"] = reports_count
        
        # Get stats
        stats = await get_signals_stats(db, hours)
        
        return {
            "ok": True,
            "items": signals,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0),
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Get signals error: {e}")
        return {"ok": False, "error": str(e)}


async def get_signals_stats(db, hours: int = 24) -> Dict[str, Any]:
    """Get signal statistics"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    total = await db.geo_signals.count_documents({"createdAt": {"$gte": cutoff}})
    confirmed = await db.geo_signals.count_documents({
        "createdAt": {"$gte": cutoff},
        "status": "confirmed"
    })
    raw = await db.geo_signals.count_documents({
        "createdAt": {"$gte": cutoff},
        "status": "raw"
    })
    dismissed = await db.geo_signals.count_documents({
        "createdAt": {"$gte": cutoff},
        "status": "dismissed"
    })
    
    # Pending moderation = raw + weak + medium (not confirmed/dismissed)
    pending = await db.geo_signals.count_documents({
        "createdAt": {"$gte": cutoff},
        "status": {"$in": ["raw", "weak", "medium"]}
    })
    
    return {
        "total": total,
        "confirmed": confirmed,
        "raw": raw,
        "dismissed": dismissed,
        "pending": pending
    }


async def get_signal_by_id(db, signal_id: str) -> Dict[str, Any]:
    """Get single signal by ID"""
    try:
        signal = await db.geo_signals.find_one(
            {"signalId": signal_id},
            {"_id": 0}
        )
        
        if not signal:
            return {"ok": False, "error": "Signal not found"}
        
        # Get reports for this signal
        reports = await db.geo_reports.find(
            {"signalId": signal_id},
            {"_id": 0}
        ).sort("createdAt", -1).to_list(50)
        
        signal["reports"] = reports
        
        return {"ok": True, "signal": signal}
    except Exception as e:
        logger.error(f"Get signal error: {e}")
        return {"ok": False, "error": str(e)}


async def confirm_signal(db, signal_id: str, admin_note: str = None) -> Dict[str, Any]:
    """Confirm signal (admin moderation)"""
    try:
        now = datetime.now(timezone.utc)
        
        update = {
            "status": "confirmed",
            "truthScore": 0.90,  # High score for admin confirmation
            "confirmedAt": now,
            "confirmedBy": "admin",
            "updatedAt": now
        }
        
        if admin_note:
            update["adminNote"] = admin_note
        
        result = await db.geo_signals.update_one(
            {"signalId": signal_id},
            {"$set": update}
        )
        
        if result.modified_count == 0:
            return {"ok": False, "error": "Signal not found"}
        
        logger.info(f"Signal confirmed: {signal_id}")
        
        return {"ok": True, "signalId": signal_id, "status": "confirmed"}
    except Exception as e:
        logger.error(f"Confirm signal error: {e}")
        return {"ok": False, "error": str(e)}


async def dismiss_signal(db, signal_id: str, reason: str = None) -> Dict[str, Any]:
    """Dismiss signal (admin moderation)"""
    try:
        now = datetime.now(timezone.utc)
        
        update = {
            "status": "dismissed",
            "truthScore": 0.0,
            "dismissedAt": now,
            "dismissedBy": "admin",
            "updatedAt": now
        }
        
        if reason:
            update["dismissReason"] = reason
        
        result = await db.geo_signals.update_one(
            {"signalId": signal_id},
            {"$set": update}
        )
        
        if result.modified_count == 0:
            return {"ok": False, "error": "Signal not found"}
        
        logger.info(f"Signal dismissed: {signal_id}")
        
        return {"ok": True, "signalId": signal_id, "status": "dismissed"}
    except Exception as e:
        logger.error(f"Dismiss signal error: {e}")
        return {"ok": False, "error": str(e)}


async def update_signal(
    db,
    signal_id: str,
    event_type: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    address: Optional[str] = None,
    truth_score: Optional[float] = None
) -> Dict[str, Any]:
    """Update signal fields (admin edit)"""
    try:
        updates = {"updatedAt": datetime.now(timezone.utc)}
        
        if event_type is not None and event_type in EVENT_TYPES:
            updates["eventType"] = event_type
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if lat is not None:
            updates["lat"] = lat
        if lng is not None:
            updates["lng"] = lng
        if address is not None:
            updates["address"] = address
        if truth_score is not None:
            updates["truthScore"] = max(0.0, min(1.0, truth_score))
        
        result = await db.geo_signals.update_one(
            {"signalId": signal_id},
            {"$set": updates}
        )
        
        if result.modified_count == 0:
            return {"ok": False, "error": "Signal not found or no changes"}
        
        logger.info(f"Signal updated: {signal_id}")
        
        return {"ok": True, "signalId": signal_id, "modified": True}
    except Exception as e:
        logger.error(f"Update signal error: {e}")
        return {"ok": False, "error": str(e)}


async def create_manual_signal(
    db,
    event_type: str,
    lat: float,
    lng: float,
    title: str = None,
    description: str = None,
    address: str = None,
    truth_score: float = 0.9
) -> Dict[str, Any]:
    """Create manual signal (admin created)"""
    try:
        now = datetime.now(timezone.utc)
        signal_id = f"signal_{secrets.token_hex(8)}"
        
        if event_type not in EVENT_TYPES:
            event_type = "unknown"
        
        signal = {
            "signalId": signal_id,
            "eventType": event_type,
            "title": title or f"Manual: {event_type}",
            "description": description or "",
            "lat": lat,
            "lng": lng,
            "address": address,
            "sourceType": "manual_admin",
            "source": "admin",
            "status": "confirmed",  # Admin signals are auto-confirmed
            "truthScore": truth_score,
            "reportsCount": 1,
            "createdAt": now,
            "updatedAt": now,
            "createdBy": "admin"
        }
        
        await db.geo_signals.insert_one(signal)
        
        # Remove _id from response (ObjectId not serializable)
        signal.pop("_id", None)
        
        logger.info(f"Manual signal created: {signal_id}")
        
        return {"ok": True, "signal": signal}
    except Exception as e:
        logger.error(f"Create manual signal error: {e}")
        return {"ok": False, "error": str(e)}


async def delete_signal(db, signal_id: str) -> Dict[str, Any]:
    """Delete signal (admin only)"""
    try:
        result = await db.geo_signals.delete_one({"signalId": signal_id})
        
        if result.deleted_count == 0:
            return {"ok": False, "error": "Signal not found"}
        
        # Also delete reports for this signal
        await db.geo_reports.delete_many({"signalId": signal_id})
        
        logger.info(f"Signal deleted: {signal_id}")
        
        return {"ok": True, "deleted": True}
    except Exception as e:
        logger.error(f"Delete signal error: {e}")
        return {"ok": False, "error": str(e)}


async def merge_signals(
    db,
    signal_ids: List[str],
    primary_signal_id: str
) -> Dict[str, Any]:
    """Merge multiple signals into one"""
    try:
        if primary_signal_id not in signal_ids:
            return {"ok": False, "error": "Primary signal must be in signal_ids"}
        
        if len(signal_ids) < 2:
            return {"ok": False, "error": "Need at least 2 signals to merge"}
        
        # Get all signals
        signals = await db.geo_signals.find(
            {"signalId": {"$in": signal_ids}},
            {"_id": 0}
        ).to_list(len(signal_ids))
        
        if len(signals) != len(signal_ids):
            return {"ok": False, "error": "Some signals not found"}
        
        # Combine reports
        total_reports = sum(s.get("reportsCount", 1) for s in signals)
        
        # Update primary signal
        now = datetime.now(timezone.utc)
        await db.geo_signals.update_one(
            {"signalId": primary_signal_id},
            {
                "$set": {
                    "reportsCount": total_reports,
                    "mergedFrom": [s for s in signal_ids if s != primary_signal_id],
                    "updatedAt": now
                }
            }
        )
        
        # Delete other signals
        other_ids = [s for s in signal_ids if s != primary_signal_id]
        await db.geo_signals.delete_many({"signalId": {"$in": other_ids}})
        
        # Move reports to primary signal
        await db.geo_reports.update_many(
            {"signalId": {"$in": other_ids}},
            {"$set": {"signalId": primary_signal_id, "merged": True}}
        )
        
        logger.info(f"Merged {len(other_ids)} signals into {primary_signal_id}")
        
        return {
            "ok": True,
            "primarySignalId": primary_signal_id,
            "mergedCount": len(other_ids),
            "totalReports": total_reports
        }
    except Exception as e:
        logger.error(f"Merge signals error: {e}")
        return {"ok": False, "error": str(e)}


async def bulk_update_status(
    db,
    signal_ids: List[str],
    status: str
) -> Dict[str, Any]:
    """Bulk update signal status"""
    try:
        if status not in SIGNAL_STATUSES:
            return {"ok": False, "error": f"Invalid status. Must be one of: {SIGNAL_STATUSES}"}
        
        now = datetime.now(timezone.utc)
        
        result = await db.geo_signals.update_many(
            {"signalId": {"$in": signal_ids}},
            {
                "$set": {
                    "status": status,
                    "updatedAt": now,
                    "bulkUpdated": True
                }
            }
        )
        
        logger.info(f"Bulk updated {result.modified_count} signals to status={status}")
        
        return {
            "ok": True,
            "modifiedCount": result.modified_count,
            "status": status
        }
    except Exception as e:
        logger.error(f"Bulk update error: {e}")
        return {"ok": False, "error": str(e)}


async def ensure_signals_indexes(db):
    """Create indexes for signals collection"""
    await db.geo_signals.create_index("signalId", unique=True)
    await db.geo_signals.create_index([("createdAt", -1)])
    await db.geo_signals.create_index("status")
    await db.geo_signals.create_index("eventType")
    await db.geo_signals.create_index("cell")
    await db.geo_signals.create_index("truthScore")
    await db.geo_signals.create_index("source")
    
    # Geo reports
    await db.geo_reports.create_index([("signalId", 1), ("userId", 1)])
    await db.geo_reports.create_index([("createdAt", -1)])
    
    logger.info("Signals indexes created")
