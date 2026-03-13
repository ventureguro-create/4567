"""
Media Engine PRO - Task 1
Production-grade media handling with:
- tg_media_assets collection (normalized)
- Safe download with size/disk guards
- Deduplication
- Garbage collector
- Storage stats
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Config from ENV
MEDIA_ROOT = os.environ.get('TG_MEDIA_ROOT', '/app/backend/public/tg/media')
MAX_MEDIA_MB = int(os.environ.get('TG_MEDIA_MAX_MB', '20'))
MEDIA_GC_DAYS = int(os.environ.get('TG_MEDIA_GC_DAYS', '30'))
DISK_SOFT_LIMIT_MB = int(os.environ.get('TG_DISK_SOFT_LIMIT_MB', '5000'))
DISK_HARD_LIMIT_MB = int(os.environ.get('TG_DISK_HARD_LIMIT_MB', '8000'))


def get_disk_usage_mb() -> float:
    """Calculate total disk usage of media folder in MB"""
    total = 0
    try:
        for root, dirs, files in os.walk(MEDIA_ROOT):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except:
                    pass
    except:
        pass
    return total / (1024 * 1024)


async def ensure_media_indexes(db):
    """Create indexes for tg_media_assets"""
    try:
        await db.tg_media_assets.create_index(
            [("username", 1), ("messageId", 1), ("kind", 1)],
            unique=True
        )
        await db.tg_media_assets.create_index([("createdAt", 1)])
        await db.tg_media_assets.create_index([("lastAccessAt", 1)])
        logger.info("Media assets indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


async def download_media_safe(
    client,
    message,
    username: str,
    db,
    max_size_mb: int = None
) -> Optional[Dict[str, Any]]:
    """
    Safely download media from Telegram message.
    
    Returns dict with media info or None if skipped/failed.
    Features:
    - Size cap
    - Dedupe by (username, messageId, kind)
    - Disk guard
    - FloodWait aware
    """
    from telethon.errors import FloodWaitError
    
    if max_size_mb is None:
        max_size_mb = MAX_MEDIA_MB
    
    if not message or not message.media:
        return None
    
    if not message.photo and not message.video:
        return None
    
    kind = "photo" if message.photo else "video"
    ext = "jpg" if kind == "photo" else "mp4"
    
    # Size guard (if known)
    if message.file and message.file.size:
        if message.file.size > max_size_mb * 1024 * 1024:
            logger.info(f"Media too large ({message.file.size / 1024 / 1024:.1f}MB), skipping")
            return None
    
    # Dedupe check in DB
    existing = await db.tg_media_assets.find_one({
        "username": username,
        "messageId": message.id,
        "kind": kind
    })
    
    # Build file path
    folder = os.path.join(MEDIA_ROOT, username)
    os.makedirs(folder, exist_ok=True)
    filename = f"{message.id}.{ext}"
    local_path = os.path.join(folder, filename)
    relative_url = f"/tg/media/{username}/{filename}"
    
    if existing and existing.get("status") == "READY":
        # Check if file still exists
        if os.path.exists(local_path):
            # Update lastAccessAt
            await db.tg_media_assets.update_one(
                {"_id": existing["_id"]},
                {"$set": {"lastAccessAt": datetime.utcnow()}}
            )
            return {
                "kind": kind,
                "localPath": relative_url,
                "size": existing.get("size"),
                "cached": True
            }
    
    # Disk guard
    if get_disk_usage_mb() > DISK_HARD_LIMIT_MB:
        logger.warning("Disk hard limit reached, skipping media download")
        return None
    
    try:
        await client.download_media(message, file=local_path)
        
        size = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        
        # Get dimensions for photos
        w, h = None, None
        if message.photo and hasattr(message.photo, 'sizes') and message.photo.sizes:
            largest = message.photo.sizes[-1]
            w = getattr(largest, 'w', None)
            h = getattr(largest, 'h', None)
        
        # Get duration for videos
        duration = None
        if message.video:
            duration = getattr(message.video, 'duration', None)
        
        # Upsert to tg_media_assets
        now = datetime.utcnow()
        await db.tg_media_assets.update_one(
            {
                "username": username,
                "messageId": message.id,
                "kind": kind
            },
            {
                "$set": {
                    "username": username,
                    "messageId": message.id,
                    "kind": kind,
                    "localPath": local_path,
                    "url": relative_url,
                    "size": size,
                    "w": w,
                    "h": h,
                    "duration": duration,
                    "mime": f"image/jpeg" if kind == "photo" else "video/mp4",
                    "status": "READY",
                    "lastAccessAt": now,
                },
                "$setOnInsert": {
                    "createdAt": now,
                    "pinned": False
                }
            },
            upsert=True
        )
        
        logger.info(f"Downloaded media: {relative_url} ({size / 1024:.1f}KB)")
        
        return {
            "kind": kind,
            "localPath": relative_url,
            "size": size,
            "w": w,
            "h": h,
            "duration": duration,
            "cached": False
        }
        
    except FloodWaitError as e:
        logger.warning(f"FloodWait on media download: {e.seconds}s")
        return None
        
    except Exception as e:
        logger.error(f"Error downloading media for {username}/{message.id}: {e}")
        
        # Mark as failed
        await db.tg_media_assets.update_one(
            {
                "username": username,
                "messageId": message.id,
                "kind": kind
            },
            {
                "$set": {
                    "status": "FAILED",
                    "error": str(e),
                    "lastAccessAt": datetime.utcnow()
                }
            },
            upsert=True
        )
        return None


async def media_garbage_collector(db) -> Dict[str, Any]:
    """
    Remove old media files not accessed recently.
    Respects pinned flag.
    """
    cutoff = datetime.utcnow() - timedelta(days=MEDIA_GC_DAYS)
    
    old_files = await db.tg_media_assets.find({
        "createdAt": {"$lt": cutoff},
        "pinned": {"$ne": True}
    }).to_list(1000)
    
    deleted = 0
    freed_bytes = 0
    
    for file in old_files:
        path = file.get("localPath")
        if path and os.path.exists(path):
            try:
                size = os.path.getsize(path)
                os.remove(path)
                freed_bytes += size
            except Exception as e:
                logger.warning(f"Failed to remove {path}: {e}")
        
        await db.tg_media_assets.delete_one({"_id": file["_id"]})
        deleted += 1
    
    logger.info(f"Media GC: deleted {deleted} files, freed {freed_bytes / 1024 / 1024:.1f}MB")
    
    return {
        "deleted": deleted,
        "freedMB": round(freed_bytes / 1024 / 1024, 2)
    }


async def get_media_stats(db) -> Dict[str, Any]:
    """Get media storage statistics"""
    total_files = await db.tg_media_assets.count_documents({})
    
    # Sum sizes
    pipeline = [
        {"$group": {"_id": None, "totalSize": {"$sum": "$size"}}}
    ]
    result = await db.tg_media_assets.aggregate(pipeline).to_list(1)
    total_size = result[0]["totalSize"] if result else 0
    
    # Count by kind
    by_kind = await db.tg_media_assets.aggregate([
        {"$group": {"_id": "$kind", "count": {"$sum": 1}}}
    ]).to_list(10)
    
    # Failed count
    failed = await db.tg_media_assets.count_documents({"status": "FAILED"})
    
    return {
        "totalFiles": total_files,
        "totalSizeMB": round(total_size / (1024 * 1024), 2),
        "diskUsageMB": round(get_disk_usage_mb(), 2),
        "diskLimitMB": DISK_HARD_LIMIT_MB,
        "byKind": {item["_id"]: item["count"] for item in by_kind},
        "failedCount": failed,
        "gcDays": MEDIA_GC_DAYS
    }
