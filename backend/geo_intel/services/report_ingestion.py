"""
Report Ingestion Service - User Signal Processing
Handles user reports from Telegram bot with validation and scoring
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import hashlib
import uuid

logger = logging.getLogger(__name__)

# Source weights
SOURCE_WEIGHTS = {
    "telegram_user": 0.40,
    "telegram_channel": 0.70,
    "admin": 1.00,
    "system_seed": 0.50,
    "external_api": 0.80
}

# Event types - emoji only
EVENT_TYPES = {
    "virus": {"emoji": "🦠", "decay_hours": 24},
    "trash": {"emoji": "🗑", "decay_hours": 72},
    "rain": {"emoji": "🌧", "decay_hours": 6},
    "block": {"emoji": "🚧", "decay_hours": 12},
    "police": {"emoji": "🚔", "decay_hours": 24}
}

# Spam limits
SPAM_LIMITS = {
    "per_hour": 10,   # 10 сигналів на годину
    "per_day": 50,    # 50 сигналів на день
    "same_zone_minutes": 10,
    "dedupe_distance_meters": 40,
    "dedupe_time_minutes": 15
}


async def ensure_report_indexes(db):
    """Create indexes for report collections"""
    try:
        # geo_user_reports
        await db.geo_user_reports.create_index([("actorId", 1), ("createdAt", -1)])
        await db.geo_user_reports.create_index([("location", "2dsphere")])
        await db.geo_user_reports.create_index([("status", 1), ("truthScore", -1)])
        await db.geo_user_reports.create_index([("clusterId", 1)])
        
        # geo_user_profiles
        await db.geo_user_profiles.create_index([("actorId", 1)], unique=True)
        await db.geo_user_profiles.create_index([("radarScore", -1)])
        
        # geo_confirmations
        await db.geo_confirmations.create_index([("reportId", 1), ("actorId", 1)], unique=True)
        await db.geo_confirmations.create_index([("reportId", 1)])
        
        logger.info("Report indexes created")
    except Exception as e:
        logger.warning(f"Report index warning: {e}")


async def get_or_create_user_profile(db, actor_id: str, username: str = None) -> Dict[str, Any]:
    """Get or create user profile with trust score"""
    now = datetime.now(timezone.utc)
    
    profile = await db.geo_user_profiles.find_one({"actorId": actor_id})
    
    if not profile:
        profile = {
            "actorId": actor_id,
            "username": username,
            "trustScore": 0.50,  # New user starts at 0.5
            "radarScore": 0,
            "level": "Новачок",
            "reportsTotal": 0,
            "reportsConfirmed": 0,
            "reportsRejected": 0,
            "confirmationsGiven": 0,
            "lastReportAt": None,
            "cooldownUntil": None,
            "createdAt": now,
            "updatedAt": now
        }
        await db.geo_user_profiles.insert_one(profile)
        logger.info(f"Created user profile for {actor_id}")
    
    return profile


async def check_spam_limits(db, actor_id: str) -> Dict[str, Any]:
    """Check if user can submit new report (anti-spam)"""
    now = datetime.now(timezone.utc)
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(hours=24)
    
    # Check cooldown
    profile = await db.geo_user_profiles.find_one({"actorId": actor_id})
    if profile and profile.get("cooldownUntil"):
        if profile["cooldownUntil"] > now:
            remaining = (profile["cooldownUntil"] - now).seconds
            return {"allowed": False, "reason": "cooldown", "remaining_seconds": remaining}
    
    # Count reports in last hour
    hour_count = await db.geo_user_reports.count_documents({
        "actorId": actor_id,
        "createdAt": {"$gte": hour_ago}
    })
    
    if hour_count >= SPAM_LIMITS["per_hour"]:
        return {"allowed": False, "reason": "hourly_limit", "count": hour_count}
    
    # Count reports in last day
    day_count = await db.geo_user_reports.count_documents({
        "actorId": actor_id,
        "createdAt": {"$gte": day_ago}
    })
    
    if day_count >= SPAM_LIMITS["per_day"]:
        return {"allowed": False, "reason": "daily_limit", "count": day_count}
    
    return {"allowed": True, "hour_count": hour_count, "day_count": day_count}


async def find_duplicate_event(db, lat: float, lng: float, event_type: str, minutes: int = 15) -> Optional[Dict]:
    """Find existing event nearby for deduplication"""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    distance_meters = SPAM_LIMITS["dedupe_distance_meters"]
    
    # Find nearby events of same type
    existing = await db.geo_user_reports.find_one({
        "eventType": event_type,
        "createdAt": {"$gte": cutoff},
        "status": {"$in": ["pending", "active", "confirmed"]},
        "location": {
            "$nearSphere": {
                "$geometry": {"type": "Point", "coordinates": [lng, lat]},
                "$maxDistance": distance_meters
            }
        }
    })
    
    return existing


def calculate_photo_hash(photo_data: bytes) -> str:
    """Calculate hash for photo deduplication"""
    return hashlib.sha256(photo_data).hexdigest()[:32]


async def create_user_report(
    db,
    actor_id: str,
    event_type: str,
    lat: float,
    lng: float,
    username: str = None,
    photo_url: str = None,
    photo_hash: str = None,
    description: str = None,
    address_text: str = None
) -> Dict[str, Any]:
    """
    Create new user report with validation and scoring
    
    Flow:
    1. Check spam limits
    2. Get/create user profile
    3. Check for duplicates (dedupe)
    4. Calculate initial truth score
    5. Save report
    """
    now = datetime.now(timezone.utc)
    
    # 1. Check spam
    spam_check = await check_spam_limits(db, actor_id)
    if not spam_check["allowed"]:
        return {"ok": False, "error": "SPAM_LIMIT", "details": spam_check}
    
    # 2. Get user profile
    profile = await get_or_create_user_profile(db, actor_id, username)
    trust_score = profile.get("trustScore", 0.50)
    
    # 3. Check for duplicates
    existing = await find_duplicate_event(db, lat, lng, event_type)
    if existing:
        # This is a confirmation, not a new report
        return await add_confirmation_to_existing(db, existing, actor_id, trust_score)
    
    # 4. Calculate initial truth score
    has_photo = photo_url is not None
    source_weight = SOURCE_WEIGHTS.get("telegram_user", 0.40)
    
    # Single source truth formula
    truth_score = (
        source_weight * 0.45 +
        (1.0 if has_photo else 0.0) * 0.20 +
        trust_score * 0.25 +
        1.0 * 0.10  # geo quality (assume good)
    )
    
    # Determine initial status
    if truth_score >= 0.70:
        status = "active"
    elif truth_score >= 0.40:
        status = "active"
    else:
        status = "pending"
    
    # 5. Create report
    report_id = str(uuid.uuid4())
    event_config = EVENT_TYPES.get(event_type, EVENT_TYPES.get("police", {"emoji": "🚔", "decay_hours": 24}))
    expires_at = now + timedelta(hours=event_config["decay_hours"])
    
    report = {
        "reportId": report_id,
        "actorId": actor_id,
        "username": username,
        "eventType": event_type,
        "eventEmoji": event_config["emoji"],
        "eventLabel": event_config["emoji"],  # Same as emoji - no text
        "lat": lat,
        "lng": lng,
        "location": {"type": "Point", "coordinates": [lng, lat]},
        "addressText": address_text,
        "description": description,
        "hasPhoto": has_photo,
        "photoUrl": photo_url,
        "photoHash": photo_hash,
        "source": "telegram_user",
        "sourceWeight": source_weight,
        "trustScore": trust_score,
        "truthScore": round(truth_score, 3),
        "spamScore": 0.0,
        "manipulationScore": 0.0,
        "confirmationCount": 0,
        "rejectCount": 0,
        "status": status,
        "clusterId": None,
        "createdAt": now,
        "updatedAt": now,
        "expiresAt": expires_at
    }
    
    await db.geo_user_reports.insert_one(report)
    
    # Update user profile
    await db.geo_user_profiles.update_one(
        {"actorId": actor_id},
        {
            "$inc": {"reportsTotal": 1},
            "$set": {"lastReportAt": now, "updatedAt": now}
        }
    )
    
    # Add to geo_events for display on map
    await sync_report_to_geo_events(db, report)
    
    logger.info(f"Created report {report_id} from {actor_id}: {event_type} at {lat},{lng} - truth={truth_score:.2f}")
    
    return {
        "ok": True,
        "reportId": report_id,
        "eventType": event_type,
        "eventEmoji": event_config["emoji"],
        "truthScore": round(truth_score, 3),
        "status": status,
        "message": "Сигнал прийнято",
        "isNew": True
    }


async def add_confirmation_to_existing(db, existing_report: Dict, actor_id: str, trust_score: float) -> Dict[str, Any]:
    """Add confirmation to existing event (dedupe merge)"""
    report_id = existing_report.get("reportId") or str(existing_report.get("_id"))
    now = datetime.now(timezone.utc)
    
    # Check if user already confirmed this
    already_confirmed = await db.geo_confirmations.find_one({
        "reportId": report_id,
        "actorId": actor_id
    })
    
    if already_confirmed:
        return {
            "ok": False,
            "error": "ALREADY_CONFIRMED",
            "message": "Ви вже підтвердили цей сигнал"
        }
    
    # Add confirmation
    await db.geo_confirmations.insert_one({
        "reportId": report_id,
        "actorId": actor_id,
        "type": "confirm",
        "trustScore": trust_score,
        "createdAt": now
    })
    
    # Update report
    new_count = existing_report.get("confirmationCount", 0) + 1
    
    # Recalculate truth score with confirmations
    confirmation_boost = min(new_count * 0.10, 0.30)  # Max +0.30 from confirmations
    new_truth = min(1.5, existing_report.get("truthScore", 0.5) + confirmation_boost * trust_score)
    
    # Update status
    new_status = existing_report.get("status", "pending")
    if new_truth >= 0.70 or new_count >= 3:
        new_status = "confirmed"
    elif new_truth >= 0.40:
        new_status = "active"
    
    await db.geo_user_reports.update_one(
        {"reportId": report_id},
        {
            "$inc": {"confirmationCount": 1},
            "$set": {
                "truthScore": round(new_truth, 3),
                "status": new_status,
                "updatedAt": now
            }
        }
    )
    
    # Update user profile
    await db.geo_user_profiles.update_one(
        {"actorId": actor_id},
        {"$inc": {"confirmationsGiven": 1}}
    )
    
    # Sync to geo_events
    existing_report["confirmationCount"] = new_count
    existing_report["truthScore"] = new_truth
    existing_report["status"] = new_status
    await sync_report_to_geo_events(db, existing_report)
    
    logger.info(f"Added confirmation to {report_id} from {actor_id}, count={new_count}, truth={new_truth:.2f}")
    
    return {
        "ok": True,
        "reportId": report_id,
        "eventType": existing_report.get("eventType"),
        "eventEmoji": existing_report.get("eventEmoji"),
        "truthScore": round(new_truth, 3),
        "confirmationCount": new_count,
        "status": new_status,
        "message": "Сигнал підтверджено",
        "isNew": False,
        "isConfirmation": True
    }


async def sync_report_to_geo_events(db, report: Dict):
    """Sync user report to geo_events for map display"""
    now = datetime.now(timezone.utc)
    
    # Determine confidence level for display
    truth = report.get("truthScore", 0.5)
    if truth >= 0.80:
        confidence_level = "high"
        confidence_label = "Високий"
        confidence_color = "green"
    elif truth >= 0.50:
        confidence_level = "medium"
        confidence_label = "Середній"
        confidence_color = "yellow"
    else:
        confidence_level = "low"
        confidence_label = "Низький"
        confidence_color = "gray"
    
    geo_event = {
        "reportId": report.get("reportId"),
        "eventType": report.get("eventType"),
        "title": f"{report.get('eventEmoji', '📍')} {report.get('eventLabel', 'Сигнал')}",
        "lat": report.get("lat"),
        "lng": report.get("lng"),
        "location": report.get("location"),
        "addressText": report.get("addressText"),
        "evidenceText": report.get("description"),
        "source": {
            "type": "user_report",
            "username": report.get("username"),
            "actorId": report.get("actorId")
        },
        "truthScore": report.get("truthScore"),
        "confidenceLevel": confidence_level,
        "confidenceLabel": confidence_label,
        "confidenceColor": confidence_color,
        "confirmationCount": report.get("confirmationCount", 0),
        "hasPhoto": report.get("hasPhoto", False),
        "photoUrl": report.get("photoUrl"),
        "status": report.get("status"),
        "createdAt": report.get("createdAt", now),
        "updatedAt": now,
        "expiresAt": report.get("expiresAt"),
        "metrics": {
            "views": 0,
            "confirmations": report.get("confirmationCount", 0)
        }
    }
    
    await db.geo_events.update_one(
        {"reportId": report.get("reportId")},
        {"$set": geo_event},
        upsert=True
    )


async def process_confirmation(
    db,
    report_id: str,
    actor_id: str,
    confirmation_type: str  # "confirm" | "reject" | "false"
) -> Dict[str, Any]:
    """Process user confirmation/rejection of a report"""
    now = datetime.now(timezone.utc)
    
    report = await db.geo_user_reports.find_one({"reportId": report_id})
    if not report:
        return {"ok": False, "error": "REPORT_NOT_FOUND"}
    
    # Check if same user
    if report.get("actorId") == actor_id:
        return {"ok": False, "error": "CANNOT_CONFIRM_OWN"}
    
    # Check if already voted
    existing = await db.geo_confirmations.find_one({
        "reportId": report_id,
        "actorId": actor_id
    })
    if existing:
        return {"ok": False, "error": "ALREADY_VOTED"}
    
    # Get confirmer's trust score
    profile = await get_or_create_user_profile(db, actor_id)
    trust_score = profile.get("trustScore", 0.50)
    
    # Save confirmation
    await db.geo_confirmations.insert_one({
        "reportId": report_id,
        "actorId": actor_id,
        "type": confirmation_type,
        "trustScore": trust_score,
        "createdAt": now
    })
    
    # Update report based on confirmation type
    update_ops = {"$set": {"updatedAt": now}}
    
    if confirmation_type == "confirm":
        update_ops["$inc"] = {"confirmationCount": 1}
        truth_boost = 0.08 * trust_score
    elif confirmation_type == "reject":
        update_ops["$inc"] = {"rejectCount": 1}
        truth_boost = -0.05 * trust_score
    else:  # false
        update_ops["$inc"] = {"rejectCount": 1, "manipulationScore": 0.15}
        truth_boost = -0.12 * trust_score
    
    # Recalculate truth score
    new_truth = max(0, min(1.5, report.get("truthScore", 0.5) + truth_boost))
    update_ops["$set"]["truthScore"] = round(new_truth, 3)
    
    # Update status
    confirm_count = report.get("confirmationCount", 0) + (1 if confirmation_type == "confirm" else 0)
    reject_count = report.get("rejectCount", 0) + (1 if confirmation_type != "confirm" else 0)
    
    if new_truth >= 0.70 or confirm_count >= 3:
        new_status = "confirmed"
    elif reject_count >= 3 or new_truth < 0.20:
        new_status = "rejected"
    elif new_truth >= 0.40:
        new_status = "active"
    else:
        new_status = "pending"
    
    update_ops["$set"]["status"] = new_status
    
    await db.geo_user_reports.update_one({"reportId": report_id}, update_ops)
    
    # Update reporter's trust score based on confirmations
    reporter_id = report.get("actorId")
    if confirmation_type == "confirm":
        await update_user_trust(db, reporter_id, +0.03)
    elif confirmation_type == "false":
        await update_user_trust(db, reporter_id, -0.10)
    
    # Sync to geo_events
    report["truthScore"] = new_truth
    report["status"] = new_status
    report["confirmationCount"] = confirm_count
    await sync_report_to_geo_events(db, report)
    
    return {
        "ok": True,
        "reportId": report_id,
        "confirmationType": confirmation_type,
        "newTruthScore": round(new_truth, 3),
        "newStatus": new_status,
        "confirmationCount": confirm_count,
        "rejectCount": reject_count
    }


async def update_user_trust(db, actor_id: str, delta: float):
    """Update user trust score with bounds"""
    profile = await db.geo_user_profiles.find_one({"actorId": actor_id})
    if not profile:
        return
    
    current = profile.get("trustScore", 0.50)
    new_trust = max(0.10, min(1.00, current + delta))
    
    # Update level based on trust
    if new_trust >= 0.90:
        level = "Експерт"
    elif new_trust >= 0.75:
        level = "Довірений"
    elif new_trust >= 0.60:
        level = "Активний"
    elif new_trust >= 0.40:
        level = "Новачок"
    else:
        level = "Під наглядом"
    
    await db.geo_user_profiles.update_one(
        {"actorId": actor_id},
        {
            "$set": {
                "trustScore": round(new_trust, 3),
                "level": level,
                "updatedAt": datetime.now(timezone.utc)
            }
        }
    )


async def update_radar_score(db, actor_id: str, points: int, reason: str):
    """Update user's radar score (gamification)"""
    await db.geo_user_profiles.update_one(
        {"actorId": actor_id},
        {
            "$inc": {"radarScore": points},
            "$set": {"updatedAt": datetime.now(timezone.utc)}
        }
    )
    
    # Log score change
    await db.geo_score_log.insert_one({
        "actorId": actor_id,
        "points": points,
        "reason": reason,
        "createdAt": datetime.now(timezone.utc)
    })


async def get_leaderboard(db, limit: int = 10) -> List[Dict]:
    """Get top reporters leaderboard"""
    leaders = await db.geo_user_profiles.find(
        {"radarScore": {"$gt": 0}},
        {"_id": 0, "actorId": 1, "username": 1, "radarScore": 1, "level": 1, "reportsConfirmed": 1}
    ).sort("radarScore", -1).limit(limit).to_list(limit)
    
    return leaders


async def get_user_stats(db, actor_id: str) -> Dict[str, Any]:
    """Get user's report statistics"""
    profile = await db.geo_user_profiles.find_one(
        {"actorId": actor_id},
        {"_id": 0}
    )
    
    if not profile:
        return {"ok": False, "error": "USER_NOT_FOUND"}
    
    return {
        "ok": True,
        "actorId": actor_id,
        "username": profile.get("username"),
        "trustScore": profile.get("trustScore", 0.50),
        "radarScore": profile.get("radarScore", 0),
        "level": profile.get("level", "Новачок"),
        "reportsTotal": profile.get("reportsTotal", 0),
        "reportsConfirmed": profile.get("reportsConfirmed", 0),
        "reportsRejected": profile.get("reportsRejected", 0),
        "confirmationsGiven": profile.get("confirmationsGiven", 0)
    }
