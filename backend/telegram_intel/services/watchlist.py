"""
Telegram Intel - Watchlist Service
Version: 1.0.0
"""

import logging
from typing import Any, Dict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def get_watchlist(db, actor_id: str = "default") -> Dict[str, Any]:
    """Get actor's watchlist"""
    try:
        items = await db.tg_watchlist.find(
            {"$or": [{"actorId": actor_id}, {"actorId": "a_public"}]},
            {"_id": 0, "username": 1, "addedAt": 1, "actorId": 1}
        ).to_list(500)
        
        return {
            "ok": True,
            "items": items,
            "total": len(items)
        }
    except Exception as e:
        logger.error(f"Watchlist error: {e}")
        return {"ok": False, "error": str(e), "items": [], "total": 0}


async def add_to_watchlist(db, username: str, actor_id: str = "a_public") -> Dict[str, Any]:
    """Add channel to watchlist"""
    try:
        clean = username.lower().replace("@", "").strip()
        
        await db.tg_watchlist.update_one(
            {"actorId": actor_id, "username": clean},
            {"$set": {"username": clean, "actorId": actor_id, "addedAt": datetime.now(timezone.utc)}},
            upsert=True
        )
        
        return {"ok": True, "username": clean}
    except Exception as e:
        logger.error(f"Add to watchlist error: {e}")
        return {"ok": False, "error": str(e)}


async def remove_from_watchlist(db, username: str, actor_id: str = "default") -> Dict[str, Any]:
    """Remove channel from watchlist"""
    try:
        clean = username.lower().replace("@", "").strip()
        
        result = await db.tg_watchlist.delete_one(
            {"actorId": actor_id, "username": clean}
        )
        
        return {"ok": True, "deleted": result.deleted_count > 0}
    except Exception as e:
        logger.error(f"Remove from watchlist error: {e}")
        return {"ok": False, "error": str(e)}
