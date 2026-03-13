"""
Media Backfill Worker - Production-safe media download
CRITICAL: Controlled, rate-limited, WATCHLIST-only

Guards:
- Only WATCHLIST channels
- Only last 14 days
- Only photos (video = thumb only)
- Max 20 downloads per tick
- 2.5s delay between downloads
- FloodWait = stop tick
- Max 8MB per file
"""
import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIG (from ENV or defaults)
# ============================================================================
MEDIA_BACKFILL_ENABLED = os.environ.get('MEDIA_BACKFILL_ENABLED', 'true').lower() == 'true'
MEDIA_BACKFILL_WINDOW_DAYS = int(os.environ.get('MEDIA_BACKFILL_WINDOW_DAYS', '14'))
MEDIA_BACKFILL_MAX_POSTS_PER_TICK = int(os.environ.get('MEDIA_BACKFILL_MAX_POSTS_PER_TICK', '50'))
MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK = int(os.environ.get('MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK', '20'))
MEDIA_BACKFILL_DELAY_SECONDS = float(os.environ.get('MEDIA_BACKFILL_DELAY_SECONDS', '2.5'))
MEDIA_BACKFILL_PHOTO_ONLY = os.environ.get('MEDIA_BACKFILL_PHOTO_ONLY', 'true').lower() == 'true'
MEDIA_MAX_FILE_BYTES = int(os.environ.get('MEDIA_MAX_FILE_BYTES', str(8 * 1024 * 1024)))

MEDIA_ROOT = Path("/app/backend/public")


async def download_photo_asset(
    db,
    client,
    username: str,
    message,
    logger
) -> Optional[Dict[str, Any]]:
    """
    Download photo from message and save to tg_media_assets.
    Returns asset info or None if failed/skipped.
    """
    now = datetime.now(timezone.utc)
    mid = message.id
    
    # Create directory
    channel_dir = MEDIA_ROOT / f"tg/media/{username}"
    channel_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = channel_dir / f"{mid}.jpg"
    
    try:
        # Download photo
        await client.download_media(message.photo, file=str(file_path))
        
        if not file_path.exists():
            logger.warning(f"Download failed: {username}/{mid}")
            return None
        
        size = file_path.stat().st_size
        
        # Size guard
        if size > MEDIA_MAX_FILE_BYTES:
            logger.info(f"File too large ({size / 1024 / 1024:.1f}MB), removing: {username}/{mid}")
            file_path.unlink(missing_ok=True)
            return None
        
        # Get dimensions if available
        w, h = None, None
        if hasattr(message.photo, 'sizes') and message.photo.sizes:
            largest = message.photo.sizes[-1]
            w = getattr(largest, 'w', None)
            h = getattr(largest, 'h', None)
        
        # Build relative URL
        rel_url = f"/tg/media/{username}/{mid}.jpg"
        
        # Upsert to DB
        asset_doc = {
            "username": username,
            "messageId": mid,
            "kind": "photo",
            "mime": "image/jpeg",
            "localPath": str(file_path),
            "url": rel_url,
            "size": size,
            "w": w,
            "h": h,
            "duration": None,
            "status": "READY",
            "createdAt": now,
            "lastAccessAt": now,
            "source": "backfill"
        }
        
        await db.tg_media_assets.update_one(
            {"username": username, "messageId": mid},
            {"$set": asset_doc},
            upsert=True
        )
        
        logger.info(f"Backfill downloaded: {username}/{mid} ({size / 1024:.1f}KB)")
        
        return {
            "username": username,
            "messageId": mid,
            "size": size,
            "url": rel_url
        }
        
    except Exception as e:
        logger.error(f"Download error {username}/{mid}: {e}")
        file_path.unlink(missing_ok=True)
        return None


async def media_backfill_tick(db, mtproto_client, logger) -> Dict[str, Any]:
    """
    Single tick of media backfill worker.
    
    SAFETY RULES:
    1. Only WATCHLIST channels
    2. Only last 14 days
    3. Only photos
    4. Max 20 downloads per tick
    5. 2.5s delay between downloads
    6. FloodWait = stop immediately
    
    Returns status dict.
    """
    from telethon.errors import FloodWaitError
    
    if not MEDIA_BACKFILL_ENABLED:
        return {"status": "disabled"}
    
    now = datetime.now(timezone.utc)
    window_from = (now - timedelta(days=MEDIA_BACKFILL_WINDOW_DAYS)).isoformat()
    
    # 1. Get WATCHLIST channels only
    watchlist = await db.tg_watchlist.find({}, {"username": 1, "_id": 0}).to_list(100)
    usernames = list(set(w.get("username", "").lower() for w in watchlist if w.get("username")))
    
    if not usernames:
        return {"status": "no_watchlist", "channels": 0}
    
    logger.info(f"Media backfill starting: {len(usernames)} watchlist channels")
    
    downloads_count = 0
    processed_posts = 0
    skipped_existing = 0
    errors = []
    
    for username in usernames:
        if downloads_count >= MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK:
            break
        
        try:
            # 2. Find posts with media but no asset in DB
            posts = await db.tg_posts.find(
                {
                    "username": username,
                    "date": {"$gte": window_from},
                    "hasMedia": True,
                    "mediaType": "photo" if MEDIA_BACKFILL_PHOTO_ONLY else {"$exists": True}
                },
                {"_id": 0, "messageId": 1, "mediaType": 1}
            ).limit(MEDIA_BACKFILL_MAX_POSTS_PER_TICK).to_list(MEDIA_BACKFILL_MAX_POSTS_PER_TICK)
            
            for post in posts:
                if downloads_count >= MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK:
                    break
                
                mid = post.get("messageId")
                if not mid:
                    continue
                
                # Check if asset already exists
                existing = await db.tg_media_assets.find_one(
                    {"username": username, "messageId": mid, "status": "READY"}
                )
                
                if existing:
                    skipped_existing += 1
                    continue
                
                # Photo only mode
                if MEDIA_BACKFILL_PHOTO_ONLY and post.get("mediaType") != "photo":
                    continue
                
                processed_posts += 1
                
                # Get message from Telegram
                try:
                    message = await mtproto_client.get_message_by_id(username, mid)
                    
                    if not message or not message.photo:
                        continue
                    
                    # Download photo
                    result = await download_photo_asset(db, mtproto_client._client, username, message, logger)
                    
                    if result:
                        downloads_count += 1
                    
                    # CRITICAL: Sleep between downloads
                    await asyncio.sleep(MEDIA_BACKFILL_DELAY_SECONDS)
                    
                except FloodWaitError as e:
                    logger.warning(f"FloodWait on backfill: {e.seconds}s - stopping tick")
                    return {
                        "status": "flood_wait",
                        "wait_seconds": e.seconds,
                        "downloads": downloads_count,
                        "processed": processed_posts
                    }
                    
                except Exception as e:
                    error_msg = f"{username}/{mid}: {str(e)[:50]}"
                    errors.append(error_msg)
                    logger.error(f"Backfill error: {error_msg}")
                    
        except Exception as e:
            logger.error(f"Channel backfill error {username}: {e}")
            errors.append(f"{username}: {str(e)[:50]}")
    
    return {
        "status": "ok",
        "channels_processed": len(usernames),
        "posts_checked": processed_posts,
        "downloads": downloads_count,
        "skipped_existing": skipped_existing,
        "errors": errors[:5],  # Limit error list
        "config": {
            "window_days": MEDIA_BACKFILL_WINDOW_DAYS,
            "max_downloads": MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK,
            "photo_only": MEDIA_BACKFILL_PHOTO_ONLY
        }
    }


async def get_backfill_status(db) -> Dict[str, Any]:
    """Get current backfill status and stats"""
    
    # Count media assets
    total_assets = await db.tg_media_assets.count_documents({})
    backfill_assets = await db.tg_media_assets.count_documents({"source": "backfill"})
    
    # Count posts with media but no asset
    watchlist = await db.tg_watchlist.find({}, {"username": 1, "_id": 0}).to_list(100)
    usernames = list(set(w.get("username", "").lower() for w in watchlist if w.get("username")))
    
    window_from = (datetime.now(timezone.utc) - timedelta(days=MEDIA_BACKFILL_WINDOW_DAYS)).isoformat()
    
    posts_with_media = await db.tg_posts.count_documents({
        "username": {"$in": usernames},
        "date": {"$gte": window_from},
        "hasMedia": True,
        "mediaType": "photo" if MEDIA_BACKFILL_PHOTO_ONLY else {"$exists": True}
    })
    
    # Estimate pending
    pending_estimate = max(0, posts_with_media - total_assets)
    
    return {
        "enabled": MEDIA_BACKFILL_ENABLED,
        "total_assets": total_assets,
        "backfill_assets": backfill_assets,
        "posts_with_media": posts_with_media,
        "pending_estimate": pending_estimate,
        "config": {
            "window_days": MEDIA_BACKFILL_WINDOW_DAYS,
            "max_downloads_per_tick": MEDIA_BACKFILL_MAX_DOWNLOADS_PER_TICK,
            "delay_seconds": MEDIA_BACKFILL_DELAY_SECONDS,
            "photo_only": MEDIA_BACKFILL_PHOTO_ONLY,
            "max_file_bytes": MEDIA_MAX_FILE_BYTES
        }
    }
