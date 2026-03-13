"""
MTProto Session Guard - Production Rules Implementation

Rules enforced:
1. Single-instance lock (only one MTProto client)
2. Environment guard (prevent accidental multi-env)
3. Session fingerprint tracking
4. Health monitoring with backoff
"""
import os
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Environment identifier
DEPLOY_ENV = os.environ.get('DEPLOY_ENV', 'development')
INSTANCE_ID = os.environ.get('INSTANCE_ID', hashlib.md5(os.uname().nodename.encode()).hexdigest()[:8])

# Lock configuration
LOCK_COLLECTION = "tg_runtime_lock"
LOCK_TTL_SECONDS = 300  # 5 minutes
LOCK_HEARTBEAT_SECONDS = 60


def get_session_fingerprint(session_string: str) -> str:
    """
    Generate fingerprint from session string (for logging without exposing session).
    Only uses first/last chars + hash.
    """
    if not session_string or len(session_string) < 20:
        return "INVALID"
    
    prefix = session_string[:4]
    suffix = session_string[-4:]
    hash_mid = hashlib.sha256(session_string.encode()).hexdigest()[:8]
    
    return f"{prefix}...{hash_mid}...{suffix}"


async def acquire_mtproto_lock(db, owner_id: str = None) -> Dict[str, Any]:
    """
    Acquire single-instance lock for MTProto client.
    
    Returns:
        {"ok": True, "lockId": ...} if acquired
        {"ok": False, "error": ..., "currentOwner": ...} if locked by another
    """
    locks = db[LOCK_COLLECTION]
    now = datetime.now(timezone.utc)
    
    owner_id = owner_id or f"{DEPLOY_ENV}_{INSTANCE_ID}"
    
    # Check for existing lock
    existing = await locks.find_one({"_id": "mtproto_singleton"})
    
    if existing:
        lock_expires = existing.get("expiresAt")
        
        # Handle naive datetime comparison
        if lock_expires:
            if lock_expires.tzinfo is None:
                lock_expires = lock_expires.replace(tzinfo=timezone.utc)
        
        if lock_expires and lock_expires > now:
            # Lock is still valid
            if existing.get("ownerId") == owner_id:
                # We own the lock, refresh it
                await locks.update_one(
                    {"_id": "mtproto_singleton"},
                    {"$set": {
                        "lastHeartbeat": now,
                        "expiresAt": now + timedelta(seconds=LOCK_TTL_SECONDS)
                    }}
                )
                return {"ok": True, "lockId": "mtproto_singleton", "refreshed": True}
            else:
                # Someone else owns the lock
                return {
                    "ok": False,
                    "error": "LOCK_HELD_BY_ANOTHER",
                    "currentOwner": existing.get("ownerId"),
                    "lockedSince": existing.get("startedAt"),
                    "expiresAt": lock_expires
                }
        else:
            # Lock expired, we can take it
            pass
    
    # Acquire or refresh lock
    try:
        await locks.update_one(
            {"_id": "mtproto_singleton"},
            {
                "$set": {
                    "ownerId": owner_id,
                    "deployEnv": DEPLOY_ENV,
                    "instanceId": INSTANCE_ID,
                    "startedAt": now,
                    "lastHeartbeat": now,
                    "expiresAt": now + timedelta(seconds=LOCK_TTL_SECONDS)
                }
            },
            upsert=True
        )
        
        logger.info(f"MTProto lock acquired by {owner_id}")
        return {"ok": True, "lockId": "mtproto_singleton", "ownerId": owner_id}
        
    except Exception as e:
        logger.error(f"Failed to acquire MTProto lock: {e}")
        return {"ok": False, "error": str(e)}


async def release_mtproto_lock(db, owner_id: str = None) -> bool:
    """Release MTProto lock"""
    locks = db[LOCK_COLLECTION]
    owner_id = owner_id or f"{DEPLOY_ENV}_{INSTANCE_ID}"
    
    result = await locks.delete_one({
        "_id": "mtproto_singleton",
        "ownerId": owner_id
    })
    
    if result.deleted_count > 0:
        logger.info(f"MTProto lock released by {owner_id}")
        return True
    return False


async def heartbeat_mtproto_lock(db, owner_id: str = None) -> bool:
    """Send heartbeat to keep lock alive"""
    locks = db[LOCK_COLLECTION]
    owner_id = owner_id or f"{DEPLOY_ENV}_{INSTANCE_ID}"
    now = datetime.now(timezone.utc)
    
    result = await locks.update_one(
        {"_id": "mtproto_singleton", "ownerId": owner_id},
        {"$set": {
            "lastHeartbeat": now,
            "expiresAt": now + timedelta(seconds=LOCK_TTL_SECONDS)
        }}
    )
    
    return result.modified_count > 0


async def check_environment_guard(db, session_fingerprint: str) -> Dict[str, Any]:
    """
    Check if session is being used in wrong environment.
    
    If session fingerprint was used in different DEPLOY_ENV, this is HIGH RISK.
    """
    guards = db["tg_session_guards"]
    
    existing = await guards.find_one({"sessionFingerprint": session_fingerprint})
    
    if existing:
        if existing.get("deployEnv") != DEPLOY_ENV:
            # DANGER: Same session used in different environment!
            return {
                "ok": False,
                "error": "ENVIRONMENT_MISMATCH",
                "warning": "Session was used in different environment!",
                "previousEnv": existing.get("deployEnv"),
                "currentEnv": DEPLOY_ENV,
                "lastSeenAt": existing.get("lastSeenAt"),
                "risk": "HIGH"
            }
    
    # Update or create guard record
    now = datetime.now(timezone.utc)
    await guards.update_one(
        {"sessionFingerprint": session_fingerprint},
        {
            "$set": {
                "sessionFingerprint": session_fingerprint,
                "deployEnv": DEPLOY_ENV,
                "instanceId": INSTANCE_ID,
                "lastSeenAt": now
            },
            "$setOnInsert": {
                "firstSeenAt": now
            }
        },
        upsert=True
    )
    
    return {"ok": True, "deployEnv": DEPLOY_ENV}


async def log_session_event(db, event_type: str, details: Dict[str, Any] = None):
    """Log session lifecycle events for audit"""
    events = db["tg_session_events"]
    
    await events.insert_one({
        "type": event_type,
        "deployEnv": DEPLOY_ENV,
        "instanceId": INSTANCE_ID,
        "timestamp": datetime.now(timezone.utc),
        "details": details or {}
    })


async def get_lock_status(db) -> Dict[str, Any]:
    """Get current lock status for monitoring"""
    locks = db[LOCK_COLLECTION]
    
    lock = await locks.find_one({"_id": "mtproto_singleton"})
    
    if not lock:
        return {"locked": False}
    
    now = datetime.now(timezone.utc)
    expires_at = lock.get("expiresAt")
    
    # Handle timezone-naive datetime from MongoDB
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    is_expired = expires_at < now if expires_at else True
    
    return {
        "locked": not is_expired,
        "ownerId": lock.get("ownerId"),
        "deployEnv": lock.get("deployEnv"),
        "startedAt": lock.get("startedAt").isoformat() if lock.get("startedAt") else None,
        "lastHeartbeat": lock.get("lastHeartbeat").isoformat() if lock.get("lastHeartbeat") else None,
        "expiresAt": expires_at.isoformat() if expires_at else None,
        "expired": is_expired
    }


# ============== Startup Validation ==============

async def validate_mtproto_startup(db, session_string: str) -> Dict[str, Any]:
    """
    Full validation before starting MTProto client.
    
    Checks:
    1. Lock availability
    2. Environment guard
    3. Session fingerprint
    
    Returns result with ok=True or error details.
    """
    fingerprint = get_session_fingerprint(session_string)
    
    # 1. Check environment guard
    env_check = await check_environment_guard(db, fingerprint)
    if not env_check.get("ok"):
        await log_session_event(db, "STARTUP_BLOCKED_ENV", env_check)
        return env_check
    
    # 2. Try to acquire lock
    lock_result = await acquire_mtproto_lock(db)
    if not lock_result.get("ok"):
        await log_session_event(db, "STARTUP_BLOCKED_LOCK", lock_result)
        return lock_result
    
    # 3. Log successful startup
    await log_session_event(db, "STARTUP_SUCCESS", {
        "fingerprint": fingerprint,
        "lockId": lock_result.get("lockId")
    })
    
    logger.info(f"MTProto startup validated: env={DEPLOY_ENV}, fingerprint={fingerprint}")
    
    return {
        "ok": True,
        "fingerprint": fingerprint,
        "deployEnv": DEPLOY_ENV,
        "instanceId": INSTANCE_ID
    }
