"""
Telegram Intel - Feed Service
Version: 1.0.0

Proxy to existing implementation in telegram_lite.
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


async def get_feed_v2(
    db,
    actor_id: str = "default",
    page: int = 1,
    limit: int = 50,
    window_days: int = 7
) -> Dict[str, Any]:
    """Get feed posts for actor"""
    try:
        # Get watchlist
        watchlist = await db.tg_watchlist.find(
            {"$or": [
                {"actorId": actor_id},
                {"actorId": "a_public"},
                {"actorId": "default"},
                {"actorId": {"$exists": False}}
            ]},
            {"username": 1, "_id": 0}
        ).to_list(500)
        
        usernames = list(set(w.get("username") for w in watchlist if w.get("username")))
        
        if not usernames:
            return {"ok": True, "items": [], "total": 0, "page": page, "pages": 1, "message": "No channels in watchlist"}
        
        # Get posts
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        skip = (page - 1) * limit
        
        posts = await db.tg_posts.find(
            {"username": {"$in": usernames}, "date": {"$gte": cutoff}}
        ).sort("date", -1).skip(skip).limit(limit).to_list(limit)
        
        total = await db.tg_posts.count_documents(
            {"username": {"$in": usernames}, "date": {"$gte": cutoff}}
        )
        
        # Build response
        items = []
        for p in posts:
            reactions = p.get("reactions", {})
            if isinstance(reactions, int):
                reactions = {"total": reactions, "top": [], "extraCount": 0}
            elif isinstance(reactions, dict):
                items_list = reactions.get("items", [])
                reactions = {
                    "total": reactions.get("total", 0),
                    "top": items_list[:3],
                    "extraCount": max(len(items_list) - 3, 0)
                }
            
            items.append({
                "messageId": p.get("messageId"),
                "username": p.get("username"),
                "date": str(p.get("date", "")),
                "text": p.get("text", ""),
                "views": p.get("views", 0),
                "forwards": p.get("forwards", 0),
                "replies": p.get("replies", 0),
                "reactions": reactions,
                "hasMedia": p.get("hasMedia", False),
                "feedScore": 0.0,
                "isPinned": False,
                "isRead": False
            })
        
        pages = (total + limit - 1) // limit if total > 0 else 1
        
        return {
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
            "hasMore": page < pages
        }
    except Exception as e:
        logger.error(f"Feed error: {e}")
        return {"ok": False, "error": str(e), "items": [], "total": 0}


async def get_feed_stats(db, actor_id: str = "default", hours: int = 24) -> Dict[str, Any]:
    """Get feed statistics"""
    try:
        watchlist = await db.tg_watchlist.find(
            {"$or": [{"actorId": actor_id}, {"actorId": "a_public"}, {"actorId": "default"}]},
            {"username": 1, "_id": 0}
        ).to_list(500)
        
        usernames = list(set(w.get("username") for w in watchlist if w.get("username")))
        channels_count = len(usernames)
        
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        posts_count = await db.tg_posts.count_documents(
            {"username": {"$in": usernames}, "date": {"$gte": cutoff}}
        ) if usernames else 0
        
        media_count = await db.tg_media_assets.count_documents(
            {"username": {"$in": usernames}}
        ) if usernames else 0
        
        pinned_count = await db.tg_feed_state.count_documents({"isPinned": True})
        
        return {
            "ok": True,
            "channelsInFeed": channels_count,
            "postsToday": posts_count,
            "mediaCount": media_count,
            "avgViews": 0,
            "pinnedCount": pinned_count,
            "unreadCount": 0,
            "hoursWindow": hours
        }
    except Exception as e:
        logger.error(f"Feed stats error: {e}")
        return {"ok": False, "error": str(e)}


async def get_feed_summary(db, hours: int = 24, llm_key: Optional[str] = None) -> Dict[str, Any]:
    """Get AI-generated feed summary"""
    return {
        "ok": True,
        "summary": None,
        "postsAnalyzed": 0,
        "channelsCount": 0,
        "hoursWindow": hours,
        "error": "LLM not configured" if not llm_key else None
    }
