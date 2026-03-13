"""
Telegram Intel - Channel Service
Version: 1.0.0
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def get_channel_full(db, username: str) -> Dict[str, Any]:
    """Get full channel data"""
    try:
        clean = username.lower().replace("@", "").strip()
        
        channel = await db.tg_channel_states.find_one(
            {"username": clean},
            {"_id": 0}
        )
        
        if not channel:
            return {"ok": False, "error": "Channel not found"}
        
        posts = await db.tg_posts.find(
            {"username": clean},
            {"_id": 0}
        ).sort("date", -1).limit(100).to_list(100)
        
        # Format posts with reactions
        formatted_posts = []
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
            
            formatted_posts.append({
                "messageId": p.get("messageId"),
                "date": str(p.get("date", "")),
                "text": p.get("text", ""),
                "views": p.get("views", 0),
                "forwards": p.get("forwards", 0),
                "replies": p.get("replies", 0),
                "reactions": reactions,
                "hasMedia": p.get("hasMedia", False)
            })
        
        return {
            "ok": True,
            "channel": {
                "username": channel.get("username"),
                "title": channel.get("title"),
                "members": channel.get("participantsCount", 0),
                "avatarUrl": channel.get("avatarUrl")
            },
            "metrics": {
                "utilityScore": channel.get("utilityScore", 50),
                "tier": channel.get("tier", "C"),
                "tierLabel": channel.get("tierLabel", "Average")
            },
            "posts": formatted_posts,
            "network": {"outgoing": [], "incoming": []},
            "activity": {},
            "growth": {}
        }
    except Exception as e:
        logger.error(f"Channel error: {e}")
        return {"ok": False, "error": str(e)}


async def get_channel_list(db, limit: int = 50, offset: int = 0, sort_by: str = "utilityScore") -> Dict[str, Any]:
    """Get list of monitored channels"""
    try:
        channels = await db.tg_channel_states.find(
            {},
            {"_id": 0, "username": 1, "title": 1, "participantsCount": 1, "utilityScore": 1, "avatarUrl": 1}
        ).sort(sort_by, -1).skip(offset).limit(limit).to_list(limit)
        
        total = await db.tg_channel_states.count_documents({})
        
        return {
            "ok": True,
            "items": channels,
            "total": total
        }
    except Exception as e:
        logger.error(f"Channel list error: {e}")
        return {"ok": False, "error": str(e), "items": [], "total": 0}
