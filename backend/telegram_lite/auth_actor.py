"""
Auth + Multi-user - Task 3
Actor-based authentication with session cookies.

Features:
- Anonymous actor creation on first visit
- HttpOnly cookie sessions
- actorId isolation for watchlist/feed_state
- Ready for future Telegram/email/wallet login
"""
import os
import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Request, Response, HTTPException

logger = logging.getLogger(__name__)

# Config from ENV
JWT_SECRET = os.environ.get('AUTH_JWT_SECRET', 'default_secret_change_me')
COOKIE_NAME = os.environ.get('AUTH_COOKIE_NAME', 'fomo_actor')
JWT_TTL_DAYS = int(os.environ.get('AUTH_JWT_TTL_DAYS', '30'))


def generate_actor_id() -> str:
    """Generate unique actor ID"""
    return "a_" + secrets.token_hex(16)


def hash_ip(ip: str) -> Optional[str]:
    """Hash IP for privacy-preserving tracking"""
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


async def ensure_auth_indexes(db):
    """Create indexes for auth collections"""
    try:
        # tg_actors
        await db.tg_actors.create_index([("actorId", 1)], unique=True)
        await db.tg_actors.create_index([("lastSeenAt", -1)])
        
        # tg_watchlist with actorId
        await db.tg_watchlist.create_index(
            [("actorId", 1), ("username", 1)],
            unique=True
        )
        await db.tg_watchlist.create_index([("actorId", 1), ("addedAt", -1)])
        
        # tg_feed_state
        await db.tg_feed_state.create_index(
            [("actorId", 1), ("postKey", 1)],
            unique=True
        )
        await db.tg_feed_state.create_index([("actorId", 1), ("updatedAt", -1)])
        
        logger.info("Auth indexes created")
    except Exception as e:
        logger.warning(f"Auth index warning: {e}")


async def get_or_create_actor(
    db,
    request: Request,
    response: Response
) -> Dict[str, Any]:
    """
    Get actor from cookie or create new anonymous actor.
    Sets cookie on response if new actor created.
    """
    # Try to get actor ID from cookie
    actor_id = request.cookies.get(COOKIE_NAME)
    
    now = datetime.utcnow()
    
    if actor_id:
        # Validate actor exists
        actor = await db.tg_actors.find_one({"actorId": actor_id})
        if actor:
            # Update lastSeenAt
            await db.tg_actors.update_one(
                {"actorId": actor_id},
                {"$set": {"lastSeenAt": now}}
            )
            return {
                "actorId": actor_id,
                "type": actor.get("type", "anonymous"),
                "isNew": False
            }
    
    # Create new anonymous actor
    actor_id = generate_actor_id()
    
    actor_doc = {
        "actorId": actor_id,
        "type": "anonymous",
        "createdAt": now,
        "lastSeenAt": now,
        "meta": {
            "userAgent": request.headers.get("user-agent", "")[:200],
            "ipHash": hash_ip(request.client.host if request.client else None)
        }
    }
    
    try:
        await db.tg_actors.insert_one(actor_doc)
    except Exception as e:
        logger.warning(f"Actor insert warning: {e}")
    
    # Set cookie
    max_age = JWT_TTL_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=COOKIE_NAME,
        value=actor_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        path="/"
    )
    
    logger.info(f"Created new actor: {actor_id}")
    
    return {
        "actorId": actor_id,
        "type": "anonymous",
        "isNew": True
    }


async def get_actor_info(db, actor_id: str) -> Optional[Dict[str, Any]]:
    """Get full actor information"""
    actor = await db.tg_actors.find_one(
        {"actorId": actor_id},
        {"_id": 0}
    )
    return actor


async def migrate_legacy_watchlist(db, default_actor_id: str = "a_public"):
    """
    Migrate watchlist entries without actorId to public actor.
    Run once during setup.
    """
    # Ensure public actor exists
    now = datetime.utcnow()
    await db.tg_actors.update_one(
        {"actorId": default_actor_id},
        {
            "$setOnInsert": {
                "actorId": default_actor_id,
                "type": "anonymous",
                "createdAt": now,
                "meta": {"migration": "legacy_watchlist"}
            },
            "$set": {"lastSeenAt": now}
        },
        upsert=True
    )
    
    # Migrate watchlist entries
    result = await db.tg_watchlist.update_many(
        {"actorId": {"$exists": False}},
        {"$set": {"actorId": default_actor_id}}
    )
    
    if result.modified_count > 0:
        logger.info(f"Migrated {result.modified_count} watchlist entries to {default_actor_id}")
    
    return result.modified_count


# ============== Actor-aware Watchlist Functions ==============

async def get_actor_watchlist(db, actor_id: str) -> list:
    """Get watchlist for specific actor"""
    items = await db.tg_watchlist.find(
        {"actorId": actor_id},
        {"_id": 0, "username": 1, "addedAt": 1}
    ).sort("addedAt", -1).to_list(500)
    return items


async def add_to_watchlist(db, actor_id: str, username: str) -> bool:
    """Add channel to actor's watchlist"""
    from .scheduler_v2 import update_channel_band
    
    username = username.lower().replace("@", "").strip()
    if not username:
        return False
    
    now = datetime.utcnow()
    
    try:
        await db.tg_watchlist.update_one(
            {"actorId": actor_id, "username": username},
            {
                "$setOnInsert": {
                    "actorId": actor_id,
                    "username": username,
                    "addedAt": now
                }
            },
            upsert=True
        )
        
        # Update scheduler band
        await update_channel_band(db, username, in_any_watchlist=True)
        
        return True
    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")
        return False


async def remove_from_watchlist(db, actor_id: str, username: str) -> bool:
    """Remove channel from actor's watchlist"""
    from .scheduler_v2 import update_channel_band
    
    username = username.lower().replace("@", "").strip()
    
    result = await db.tg_watchlist.delete_one({
        "actorId": actor_id,
        "username": username
    })
    
    if result.deleted_count > 0:
        # Check if anyone else is watching this channel
        watch_count = await db.tg_watchlist.count_documents({"username": username})
        await update_channel_band(db, username, in_any_watchlist=(watch_count > 0))
        return True
    
    return False


async def check_in_watchlist(db, actor_id: str, username: str) -> bool:
    """Check if channel is in actor's watchlist"""
    username = username.lower().replace("@", "").strip()
    doc = await db.tg_watchlist.find_one({
        "actorId": actor_id,
        "username": username
    })
    return doc is not None


# ============== Actor-aware Feed State Functions ==============

async def get_feed_states(db, actor_id: str, post_keys: list) -> Dict[str, Dict]:
    """Get read/pin states for multiple posts"""
    if not post_keys:
        return {}
    
    states = await db.tg_feed_state.find({
        "actorId": actor_id,
        "postKey": {"$in": post_keys}
    }, {"_id": 0, "postKey": 1, "isRead": 1, "isPinned": 1}).to_list(len(post_keys))
    
    return {s["postKey"]: s for s in states}


async def set_post_read(db, actor_id: str, post_key: str, is_read: bool = True) -> bool:
    """Mark post as read/unread"""
    now = datetime.utcnow()
    
    await db.tg_feed_state.update_one(
        {"actorId": actor_id, "postKey": post_key},
        {
            "$set": {
                "actorId": actor_id,
                "postKey": post_key,
                "isRead": is_read,
                "updatedAt": now
            }
        },
        upsert=True
    )
    return True


async def set_post_pinned(db, actor_id: str, post_key: str, is_pinned: bool = True) -> bool:
    """Pin/unpin a post"""
    now = datetime.utcnow()
    
    await db.tg_feed_state.update_one(
        {"actorId": actor_id, "postKey": post_key},
        {
            "$set": {
                "actorId": actor_id,
                "postKey": post_key,
                "isPinned": is_pinned,
                "updatedAt": now
            }
        },
        upsert=True
    )
    return True


async def get_pinned_posts(db, actor_id: str, limit: int = 50) -> list:
    """Get pinned post keys for actor"""
    pinned = await db.tg_feed_state.find(
        {"actorId": actor_id, "isPinned": True},
        {"_id": 0, "postKey": 1}
    ).limit(limit).to_list(limit)
    
    return [p["postKey"] for p in pinned]
