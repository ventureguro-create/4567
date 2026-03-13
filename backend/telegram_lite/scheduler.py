"""
Telegram Scheduler - Production Grade
- Round-robin с приоритетом по utilityScore
- Budget management (запросы в час)
- Adaptive backoff при ошибках
- Lock механизм для каналов
- FLOOD_WAIT handling
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Config
BATCH_SIZE = 20
BASE_DELAY_MS = 2500
MAX_DELAY_MS = 15000
BUDGET_PER_60M = 600  # запросов в час
COST_FETCH = 10
COST_SNAPSHOT = 1
COST_EDGES = 1

STATE_COL = "tg_scheduler_state"
CHANNELS_COL = "tg_channel_states"

_scheduler_task = None
_scheduler_running = False


def utcnow():
    """Return naive UTC datetime"""
    return datetime.utcnow()


async def get_state(db) -> Dict[str, Any]:
    """Get or create scheduler state"""
    col = db[STATE_COL]
    st = await col.find_one({"_id": "global"})
    if not st:
        st = {
            "_id": "global",
            "enabled": False,
            "running": False,
            "lastTick": None,
            "lastError": None,
            "budgetUsed": 0,
            "budgetWindowStart": utcnow(),
            "delayMs": BASE_DELAY_MS,
            "processedLastBatch": 0,
            "totalProcessed": 0,
        }
        await col.insert_one(st)
    return st


async def set_state(db, patch: Dict[str, Any]):
    """Update scheduler state"""
    await db[STATE_COL].update_one(
        {"_id": "global"},
        {"$set": patch}
    )


def window_expired(start) -> bool:
    """Check if 60min budget window expired"""
    if not start:
        return True
    
    # Handle string format
    if isinstance(start, str):
        try:
            start = datetime.fromisoformat(start.replace('Z', '+00:00').replace('+00:00', ''))
        except:
            return True
    
    # Handle datetime
    if isinstance(start, datetime):
        # Remove timezone info for comparison
        start_naive = start.replace(tzinfo=None) if start.tzinfo else start
        return (utcnow() - start_naive).total_seconds() > 3600
    
    return True


async def ensure_budget(db, cost: int) -> bool:
    """Check and consume budget"""
    st = await get_state(db)
    
    if window_expired(st.get("budgetWindowStart")):
        await set_state(db, {
            "budgetUsed": 0,
            "budgetWindowStart": utcnow(),
            "delayMs": BASE_DELAY_MS
        })
        return True
    
    if (st.get("budgetUsed", 0) + cost) > BUDGET_PER_60M:
        return False
    
    await set_state(db, {"budgetUsed": st.get("budgetUsed", 0) + cost})
    return True


def calc_next_due_at(utility_score: float) -> datetime:
    """Calculate next due time based on utility score"""
    now = utcnow()
    u = float(utility_score or 0)
    
    if u >= 80:
        hours = 12
    elif u >= 60:
        hours = 24
    else:
        hours = 48
    
    return now + timedelta(hours=hours)


async def pick_batch(db) -> List[Dict]:
    """Pick next batch of channels to process"""
    now = utcnow()
    
    # Eligible filter - check both eligibility formats
    filter_query = {
        "$or": [
            {"eligibility.status": "ELIGIBLE"},
            {"eligible": True},
            {"eligibility": {"$exists": False}, "participantsCount": {"$gte": 1000}},
        ],
        "participantsCount": {"$gte": 1000},
    }
    
    # Get all eligible channels
    channels = await db[CHANNELS_COL].find(
        filter_query,
        {"_id": 0}
    ).sort([
        ("nextDueAt", 1),
        ("utilityScore", -1)
    ]).limit(BATCH_SIZE * 2).to_list(BATCH_SIZE * 2)
    
    # Filter for due channels (nextDueAt is null or past)
    result = []
    for ch in channels:
        next_due = ch.get("nextDueAt")
        if next_due is not None:
            # Make naive for comparison
            if hasattr(next_due, 'tzinfo') and next_due.tzinfo:
                next_due = next_due.replace(tzinfo=None)
            if next_due > now:
                continue
        result.append(ch)
        if len(result) >= BATCH_SIZE:
            break
    
    return result


async def lock_channel(db, username: str, minutes: int = 20) -> bool:
    """Try to lock channel for processing"""
    until = utcnow() + timedelta(minutes=minutes)
    now = utcnow()
    
    result = await db[CHANNELS_COL].update_one(
        {
            "username": username,
            "$or": [
                {"lockUntil": {"$exists": False}},
                {"lockUntil": None},
                {"lockUntil": {"$lte": now}}
            ]
        },
        {"$set": {"lockUntil": until}}
    )
    return result.modified_count == 1 or result.matched_count == 1


async def unlock_channel(db, username: str):
    """Release channel lock"""
    await db[CHANNELS_COL].update_one(
        {"username": username},
        {"$set": {"lockUntil": None}}
    )


async def bump_delay_on_error(db):
    """Increase delay after error"""
    st = await get_state(db)
    current = st.get("delayMs", BASE_DELAY_MS)
    next_delay = min(MAX_DELAY_MS, int(current * 1.35))
    await set_state(db, {"delayMs": next_delay})
    logger.warning(f"Scheduler delay bumped to {next_delay}ms")


async def relax_delay_on_success(db):
    """Decrease delay after success"""
    st = await get_state(db)
    current = st.get("delayMs", BASE_DELAY_MS)
    next_delay = max(BASE_DELAY_MS, int(current * 0.92))
    await set_state(db, {"delayMs": next_delay})


async def process_one(db, mtproto_client, ch: Dict, write_members_history, build_snapshot, extract_edges=None, refresh_avatar=None) -> Dict:
    """Process single channel with avatar refresh and sector classification"""
    username = ch.get("username")
    if not username:
        return {"ok": False, "error": "no username"}
    
    # Try to lock
    got_lock = await lock_channel(db, username)
    if not got_lock:
        return {"ok": False, "skipped": True}
    
    try:
        # Check budget
        cost = COST_FETCH + COST_SNAPSHOT + COST_EDGES
        budget_ok = await ensure_budget(db, cost)
        if not budget_ok:
            await unlock_channel(db, username)
            return {"ok": False, "budget": True}
        
        # MTProto fetch
        logger.info(f"[SCHED] Fetching {username}")
        
        info = await mtproto_client.get_channel_info(username)
        
        if not info or info.get("error"):
            # Channel not found or private
            await db[CHANNELS_COL].update_one(
                {"username": username},
                {
                    "$set": {
                        "eligibility.status": "EXCLUDED",
                        "excludeReason": "NOT_FOUND_OR_PRIVATE",
                        "lastFetchedAt": utcnow(),
                        "nextDueAt": utcnow() + timedelta(days=7),
                    },
                    "$inc": {"fetchFailCount": 1}
                }
            )
            await unlock_channel(db, username)
            return {"ok": False, "notFound": True}
        
        # Write members history
        members = info.get("participantsCount", 0)
        if members > 0:
            await write_members_history(db, username, members)
        
        # Update channel state
        await db[CHANNELS_COL].update_one(
            {"username": username},
            {
                "$set": {
                    "title": info.get("title", username),
                    "about": info.get("about", ""),
                    "participantsCount": members,
                    "isChannel": info.get("isChannel", True),
                    "lastFetchedAt": utcnow(),
                    "fetchFailCount": 0,
                    "nextDueAt": calc_next_due_at(ch.get("utilityScore", 50)),
                    "updatedAt": utcnow(),
                }
            }
        )
        
        # Build snapshot
        try:
            await build_snapshot(username)
        except Exception as e:
            logger.warning(f"Snapshot build failed for {username}: {e}")
        
        # Refresh avatar if function provided
        avatar_url = None
        if refresh_avatar:
            try:
                avatar_url = await refresh_avatar(mtproto_client, username)
                if avatar_url:
                    await db[CHANNELS_COL].update_one(
                        {"username": username},
                        {"$set": {"avatarUrl": avatar_url, "avatarUpdatedAt": utcnow()}}
                    )
                    logger.info(f"[SCHED] Avatar updated for {username}")
            except Exception as e:
                logger.warning(f"Avatar refresh failed for {username}: {e}")
        
        # Extract edges from posts
        if extract_edges:
            try:
                await extract_edges(db, username)
            except Exception as e:
                logger.warning(f"Edge extraction failed for {username}: {e}")
        
        await relax_delay_on_success(db)
        await unlock_channel(db, username)
        
        logger.info(f"[SCHED] OK {username}: {members:,} members")
        return {"ok": True, "username": username, "members": members}
        
    except Exception as e:
        error_msg = str(e)
        import traceback
        logger.error(f"[SCHED] Error on {username}: {error_msg}\n{traceback.format_exc()}")
        
        # FLOOD_WAIT handling
        if "FLOOD_WAIT" in error_msg or "420" in error_msg:
            await bump_delay_on_error(db)
            await set_state(db, {"lastError": f"FLOOD_WAIT on {username}: {error_msg}"})
            logger.error(f"[SCHED] FLOOD_WAIT on {username}")
        else:
            await set_state(db, {"lastError": f"ERR on {username}: {error_msg}"})
            logger.error(f"[SCHED] Error on {username}: {error_msg}")
        
        # Mark channel with next due
        await db[CHANNELS_COL].update_one(
            {"username": username},
            {
                "$set": {
                    "lastFetchedAt": utcnow(),
                    "nextDueAt": utcnow() + timedelta(hours=6),
                },
                "$inc": {"fetchFailCount": 1}
            }
        )
        
        await unlock_channel(db, username)
        return {"ok": False, "error": error_msg}


async def scheduler_tick(db, mtproto_client, write_members_history, build_snapshot, extract_edges=None, refresh_avatar=None):
    """Single scheduler tick - process one batch"""
    st = await get_state(db)
    if not st.get("enabled"):
        return {"processed": 0, "skipped": "disabled"}
    
    await set_state(db, {
        "running": True,
        "lastTick": utcnow(),
        "processedLastBatch": 0
    })
    
    batch = await pick_batch(db)
    processed = 0
    results = []
    
    logger.info(f"[SCHED] Tick starting, batch size: {len(batch)}")
    
    for ch in batch:
        st2 = await get_state(db)
        if not st2.get("enabled"):
            break
            
        delay_ms = st2.get("delayMs", BASE_DELAY_MS)
        
        result = await process_one(db, mtproto_client, ch, write_members_history, build_snapshot, extract_edges, refresh_avatar)
        results.append(result)
        
        if result.get("ok"):
            processed += 1
        
        # Budget exhausted - stop
        if result.get("budget"):
            logger.warning("[SCHED] Budget exhausted, stopping tick")
            break
        
        # Delay between requests
        await asyncio.sleep(delay_ms / 1000)
    
    total = (await get_state(db)).get("totalProcessed", 0)
    await set_state(db, {
        "running": False,
        "processedLastBatch": processed,
        "totalProcessed": total + processed
    })
    
    logger.info(f"[SCHED] Tick complete, processed: {processed}")
    return {"processed": processed, "results": results}


async def scheduler_loop(db, mtproto_client, write_members_history, build_snapshot, extract_edges=None, refresh_avatar=None):
    """Main scheduler loop"""
    global _scheduler_running
    
    logger.info("[SCHED] Loop started")
    
    while _scheduler_running:
        try:
            st = await get_state(db)
            if st.get("enabled"):
                await scheduler_tick(db, mtproto_client, write_members_history, build_snapshot, extract_edges, refresh_avatar)
        except Exception as e:
            logger.error(f"[SCHED] Loop error: {e}")
            await set_state(db, {"lastError": str(e)})
        
        # Wait 30 seconds between ticks
        await asyncio.sleep(30)
    
    logger.info("[SCHED] Loop stopped")


async def start_scheduler(db, mtproto_client, write_members_history, build_snapshot, extract_edges=None, refresh_avatar=None):
    """Start scheduler background task"""
    global _scheduler_task, _scheduler_running
    
    if _scheduler_task and not _scheduler_task.done():
        logger.warning("[SCHED] Already running")
        return False
    
    await set_state(db, {"enabled": True})
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(
        scheduler_loop(db, mtproto_client, write_members_history, build_snapshot, extract_edges, refresh_avatar)
    )
    logger.info("[SCHED] Started")
    return True


async def stop_scheduler(db):
    """Stop scheduler"""
    global _scheduler_task, _scheduler_running
    
    _scheduler_running = False
    await set_state(db, {"running": False, "enabled": False})
    
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None
    
    logger.info("[SCHED] Stopped")
    return True
