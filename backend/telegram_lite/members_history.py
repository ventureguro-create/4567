"""
Members History Module - Track subscriber growth over time
"""
import logging
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def utcnow():
    """Return naive UTC datetime"""
    return datetime.utcnow()


def date_iso(d: datetime = None) -> str:
    """Return date as YYYY-MM-DD string"""
    if d is None:
        d = utcnow()
    return d.strftime('%Y-%m-%d')


def add_days(d: datetime, days: int) -> datetime:
    """Add days to datetime"""
    return d + timedelta(days=days)


async def write_members_history(db, username: str, members: int) -> Dict[str, Any]:
    """
    Write daily members snapshot to history.
    Called after successful MTProto fetch of channel profile.
    """
    today = date_iso()
    
    doc = {
        "username": username.lower(),
        "date": today,
        "members": int(members or 0),
        "ts": utcnow()
    }
    
    await db.tg_channel_members_history.update_one(
        {"username": username.lower(), "date": today},
        {"$set": doc},
        upsert=True
    )
    
    logger.info(f"Members history written: {username} = {members} on {today}")
    return doc


async def calculate_growth(db, username: str) -> Dict[str, Any]:
    """
    Calculate growth rates from members history.
    Returns growth7/growth30 as decimals (0.05 = 5%)
    """
    History = db.tg_channel_members_history
    now = utcnow()
    
    today_str = date_iso(now)
    d7_str = date_iso(add_days(now, -7))
    d30_str = date_iso(add_days(now, -30))
    
    # Fetch history records
    t, h7, h30 = await asyncio.gather(
        History.find_one({"username": username.lower(), "date": today_str}),
        History.find_one({"username": username.lower(), "date": d7_str}),
        History.find_one({"username": username.lower(), "date": d30_str}),
    )
    
    current = t.get("members") if t else None
    base7 = h7.get("members") if h7 else None
    base30 = h30.get("members") if h30 else None
    
    # Calculate growth rates
    growth7 = None
    growth30 = None
    
    if current is not None and base7 is not None and base7 > 0:
        growth7 = (current - base7) / base7
    
    if current is not None and base30 is not None and base30 > 0:
        growth30 = (current - base30) / base30
    
    return {
        "currentMembers": current,
        "base7": base7,
        "base30": base30,
        "growth7": growth7,
        "growth30": growth30
    }


async def ensure_members_history_indexes(db):
    """Create indexes for members history collection"""
    try:
        # Unique index on username + date
        await db.tg_channel_members_history.create_index(
            [("username", 1), ("date", 1)],
            unique=True,
            background=True
        )
        
        # Index for date queries
        await db.tg_channel_members_history.create_index(
            [("date", 1)],
            background=True
        )
        
        logger.info("Members history indexes created")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")


async def get_members_history(db, username: str, days: int = 30) -> list:
    """Get members history for a channel"""
    since = date_iso(add_days(datetime.now(timezone.utc), -days))
    
    cursor = db.tg_channel_members_history.find(
        {"username": username.lower(), "date": {"$gte": since}},
        {"_id": 0}
    ).sort("date", 1)
    
    return await cursor.to_list(days + 1)
