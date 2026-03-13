"""
Geo Admin - Channels Service
Manage Telegram channels for geo parsing
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# MTProto client for live search
MTPROTO_AVAILABLE = False
MTProtoConnection = None

try:
    from telegram_lite.mtproto_client import get_mtproto_client, MTProtoConnection
    MTPROTO_AVAILABLE = True
except ImportError:
    logger.warning("MTProto client not available for channel search")


async def get_channels(
    db,
    page: int = 1,
    limit: int = 50,
    status: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Get list of channels with stats"""
    try:
        query = {}
        
        if status == "active":
            query["enabled"] = True
        elif status == "paused":
            query["enabled"] = False
        
        if search:
            query["$or"] = [
                {"username": {"$regex": search, "$options": "i"}},
                {"title": {"$regex": search, "$options": "i"}}
            ]
        
        skip = (page - 1) * limit
        total = await db.geo_channels.count_documents(query)
        
        channels = await db.geo_channels.find(
            query,
            {"_id": 0}
        ).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
        
        # Enrich with geo event counts
        for ch in channels:
            username = ch.get("username")
            if username:
                ch["geoEventsCount"] = await db.tg_geo_events.count_documents({
                    "source": username
                })
                ch["postsCount"] = await db.tg_posts.count_documents({
                    "username": username
                })
        
        return {
            "ok": True,
            "items": channels,
            "total": total,
            "page": page,
            "pages": (total // limit) + (1 if total % limit else 0)
        }
    except Exception as e:
        logger.error(f"Get channels error: {e}")
        return {"ok": False, "error": str(e)}


async def add_channel(db, username: str, priority: int = 5, tags: List[str] = None) -> Dict[str, Any]:
    """Add channel for geo monitoring with MTProto lookup"""
    try:
        username = username.lower().strip().replace("@", "")
        
        existing = await db.geo_channels.find_one({"username": username})
        if existing:
            return {"ok": False, "error": "Channel already exists"}
        
        now = datetime.now(timezone.utc)
        
        # Try to fetch channel info via MTProto
        channel_info = None
        avatar_url = None
        
        if MTPROTO_AVAILABLE and MTProtoConnection:
            try:
                async with MTProtoConnection() as client:
                    info = await client.get_channel_info(username)
                    if info and 'error' not in info:
                        channel_info = info
                        # Try to download avatar
                        try:
                            avatar_url = await client.download_profile_photo(username)
                        except Exception as avatar_err:
                            logger.warning(f"Avatar download failed: {avatar_err}")
                        
                        # Also save to tg_channel_states
                        await db.tg_channel_states.update_one(
                            {"username": username},
                            {
                                "$set": {
                                    "username": username,
                                    "title": info['title'],
                                    "about": info.get('about', ''),
                                    "participantsCount": info['participantsCount'],
                                    "isChannel": info['isChannel'],
                                    "avatarUrl": avatar_url,
                                    "lastMtprotoFetch": now,
                                    "updatedAt": now,
                                },
                                "$setOnInsert": {"createdAt": now, "stage": "QUALIFIED"}
                            },
                            upsert=True
                        )
            except Exception as e:
                logger.warning(f"MTProto lookup failed for {username}: {e}")
        
        doc = {
            "username": username,
            "title": channel_info['title'] if channel_info else username,
            "avatarUrl": avatar_url,
            "participantsCount": channel_info['participantsCount'] if channel_info else None,
            "isChannel": channel_info.get('isChannel', True) if channel_info else True,
            "enabled": True,
            "priority": priority,
            "tags": tags or [],
            "geoEventsExtracted": 0,
            "lastParsedAt": None,
            "createdAt": now,
            "updatedAt": now
        }
        
        await db.geo_channels.insert_one(doc)
        
        # Remove _id for response
        doc.pop('_id', None)
        
        return {"ok": True, "channel": doc, "mtprotoFetched": channel_info is not None}
    except Exception as e:
        logger.error(f"Add channel error: {e}")
        return {"ok": False, "error": str(e)}


async def update_channel(
    db,
    username: str,
    enabled: Optional[bool] = None,
    priority: Optional[int] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Update channel settings"""
    try:
        username = username.lower().strip()
        
        updates = {"updatedAt": datetime.now(timezone.utc)}
        
        if enabled is not None:
            updates["enabled"] = enabled
        if priority is not None:
            updates["priority"] = priority
        if tags is not None:
            updates["tags"] = tags
        
        result = await db.geo_channels.update_one(
            {"username": username},
            {"$set": updates}
        )
        
        if result.modified_count == 0:
            return {"ok": False, "error": "Channel not found"}
        
        return {"ok": True, "modified": True}
    except Exception as e:
        logger.error(f"Update channel error: {e}")
        return {"ok": False, "error": str(e)}


async def delete_channel(db, username: str) -> Dict[str, Any]:
    """Delete channel"""
    try:
        username = username.lower().strip()
        result = await db.geo_channels.delete_one({"username": username})
        
        return {"ok": True, "deleted": result.deleted_count > 0}
    except Exception as e:
        logger.error(f"Delete channel error: {e}")
        return {"ok": False, "error": str(e)}


async def get_channel_stats(db, username: str) -> Dict[str, Any]:
    """Get detailed channel statistics"""
    try:
        username = username.lower().strip()
        
        channel = await db.geo_channels.find_one(
            {"username": username},
            {"_id": 0}
        )
        
        if not channel:
            return {"ok": False, "error": "Channel not found"}
        
        # Get posts count
        posts_count = await db.tg_posts.count_documents({"username": username})
        
        # Get geo events count
        geo_events = await db.tg_geo_events.count_documents({"source": username})
        
        # Get telegram intel state
        tg_state = await db.tg_channel_states.find_one(
            {"username": username},
            {"_id": 0, "participantsCount": 1, "title": 1, "avatarUrl": 1}
        )
        
        return {
            "ok": True,
            "channel": channel,
            "stats": {
                "postsCount": posts_count,
                "geoEventsCount": geo_events,
                "members": tg_state.get("participantsCount") if tg_state else None,
                "title": tg_state.get("title") if tg_state else channel.get("title"),
                "avatarUrl": tg_state.get("avatarUrl") if tg_state else None,
            }
        }
    except Exception as e:
        logger.error(f"Channel stats error: {e}")
        return {"ok": False, "error": str(e)}



async def search_channel_live(db, username: str) -> Dict[str, Any]:
    """
    Live search channel via MTProto
    Returns channel info from Telegram if found
    """
    try:
        username = username.lower().strip().replace("@", "")
        
        if len(username) < 3:
            return {"ok": False, "error": "Username too short (min 3 chars)"}
        
        # First check if already in our database
        existing_in_geo = await db.geo_channels.find_one({"username": username})
        existing_in_states = await db.tg_channel_states.find_one(
            {"username": username},
            {"_id": 0, "username": 1, "title": 1, "avatarUrl": 1, "participantsCount": 1}
        )
        
        # If we have it in states, return it
        if existing_in_states:
            return {
                "ok": True,
                "source": "cache",
                "channel": existing_in_states,
                "alreadyAdded": existing_in_geo is not None
            }
        
        # Try MTProto live lookup
        if not MTPROTO_AVAILABLE or not MTProtoConnection:
            return {"ok": False, "error": "MTProto not available"}
        
        try:
            async with MTProtoConnection() as client:
                info = await client.get_channel_info(username)
                
                if info and 'error' not in info:
                    return {
                        "ok": True,
                        "source": "mtproto",
                        "channel": {
                            "username": info['username'],
                            "title": info['title'],
                            "participantsCount": info['participantsCount'],
                            "isChannel": info.get('isChannel', True),
                            "about": info.get('about', '')
                        },
                        "alreadyAdded": existing_in_geo is not None
                    }
                else:
                    error_type = info.get('error', 'UNKNOWN') if info else 'UNKNOWN'
                    return {
                        "ok": False, 
                        "error": error_type,
                        "message": f"Channel @{username} not found" if error_type == 'NOT_FOUND' else f"Error: {error_type}"
                    }
                    
        except Exception as e:
            logger.error(f"MTProto search error: {e}")
            return {"ok": False, "error": str(e)}
            
    except Exception as e:
        logger.error(f"Search channel error: {e}")
        return {"ok": False, "error": str(e)}
