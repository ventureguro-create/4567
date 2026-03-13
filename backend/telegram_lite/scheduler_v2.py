"""
Scheduler v2 - Task 2
Dual-loop scheduler with BASE and WATCHLIST priority bands.

BASE LOOP: Updates all eligible channels slowly (24-72h)
WATCHLIST LOOP: Updates watched channels fast (1-3h)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

import os

# Config from ENV
BASE_UNITS_PER_HOUR = int(os.environ.get('SCHEDULER_BASE_UNITS_PER_HOUR', '400'))
WATCHLIST_UNITS_PER_HOUR = int(os.environ.get('SCHEDULER_WATCHLIST_UNITS_PER_HOUR', '200'))
FETCH_COST = int(os.environ.get('SCHEDULER_FETCH_COST', '12'))

QUEUE_COL = "tg_scheduler_queue"


def utcnow():
    return datetime.utcnow()


async def ensure_scheduler_indexes(db):
    """Create indexes for scheduler queue"""
    try:
        await db[QUEUE_COL].create_index(
            [("priorityBand", 1), ("nextDueAt", 1)]
        )
        await db[QUEUE_COL].create_index(
            [("username", 1)],
            unique=True
        )
        logger.info("Scheduler v2 indexes created")
    except Exception as e:
        logger.warning(f"Scheduler index warning: {e}")


async def get_scheduler_state_v2(db) -> Dict[str, Any]:
    """Get scheduler v2 status"""
    queue = db[QUEUE_COL]
    
    now = utcnow()
    
    # Count by band
    base_total = await queue.count_documents({"priorityBand": "BASE"})
    watch_total = await queue.count_documents({"priorityBand": "WATCHLIST"})
    
    # Due now
    base_due = await queue.count_documents({
        "priorityBand": "BASE",
        "nextDueAt": {"$lte": now}
    })
    watch_due = await queue.count_documents({
        "priorityBand": "WATCHLIST",
        "nextDueAt": {"$lte": now}
    })
    
    # In cooldown
    in_cooldown = await queue.count_documents({
        "cooldownUntil": {"$gt": now}
    })
    
    # With errors
    with_errors = await queue.count_documents({
        "errorCount": {"$gt": 0}
    })
    
    return {
        "ok": True,
        "bands": {
            "BASE": {
                "total": base_total,
                "due": base_due,
                "budgetPerHour": BASE_UNITS_PER_HOUR
            },
            "WATCHLIST": {
                "total": watch_total,
                "due": watch_due,
                "budgetPerHour": WATCHLIST_UNITS_PER_HOUR
            }
        },
        "inCooldown": in_cooldown,
        "withErrors": with_errors,
        "fetchCost": FETCH_COST,
        "timestamp": now.isoformat()
    }


async def update_channel_band(db, username: str, in_any_watchlist: bool):
    """
    Update channel's priority band based on watchlist status.
    Called when user adds/removes from watchlist.
    """
    queue = db[QUEUE_COL]
    
    new_band = "WATCHLIST" if in_any_watchlist else "BASE"
    
    await queue.update_one(
        {"username": username},
        {
            "$set": {"priorityBand": new_band},
            "$setOnInsert": {
                "username": username,
                "nextDueAt": utcnow(),
                "lastFetchedAt": None,
                "errorCount": 0,
                "cooldownUntil": None,
                "utilityScore": 50
            }
        },
        upsert=True
    )
    
    logger.info(f"Channel {username} band updated to {new_band}")


async def ensure_channel_in_queue(db, username: str, utility_score: float = 50):
    """Ensure channel exists in scheduler queue"""
    queue = db[QUEUE_COL]
    
    # Check if in any watchlist
    watch_count = await db.tg_watchlist.count_documents({"username": username})
    band = "WATCHLIST" if watch_count > 0 else "BASE"
    
    await queue.update_one(
        {"username": username},
        {
            "$set": {
                "utilityScore": utility_score,
                "priorityBand": band
            },
            "$setOnInsert": {
                "username": username,
                "nextDueAt": utcnow(),
                "lastFetchedAt": None,
                "errorCount": 0,
                "cooldownUntil": None
            }
        },
        upsert=True
    )


async def update_next_due(db, username: str, band: str, success: bool = True):
    """Update next due time after processing"""
    queue = db[QUEUE_COL]
    now = utcnow()
    
    if band == "WATCHLIST":
        delay = timedelta(hours=2)  # Fast refresh for watched channels
    else:
        delay = timedelta(hours=24)  # Slow refresh for base
    
    update = {
        "lastFetchedAt": now,
        "nextDueAt": now + delay,
    }
    
    if success:
        update["errorCount"] = 0
        update["cooldownUntil"] = None
    
    await queue.update_one(
        {"username": username},
        {"$set": update}
    )


async def handle_fetch_error(db, username: str, error_msg: str, flood_seconds: int = None):
    """Handle error during channel fetch"""
    queue = db[QUEUE_COL]
    now = utcnow()
    
    update = {
        "$inc": {"errorCount": 1}
    }
    
    if flood_seconds:
        # FloodWait - set cooldown
        cooldown = now + timedelta(seconds=flood_seconds + 60)
        update["$set"] = {"cooldownUntil": cooldown}
        logger.warning(f"Channel {username} in cooldown for {flood_seconds + 60}s")
    else:
        # Regular error - short cooldown
        cooldown = now + timedelta(minutes=30)
        update["$set"] = {"cooldownUntil": cooldown}
    
    await queue.update_one(
        {"username": username},
        update
    )


async def pick_batch_v2(db, band: str, limit: int = 20) -> List[Dict]:
    """Pick next batch of channels to process from specific band"""
    queue = db[QUEUE_COL]
    now = utcnow()
    
    channels = await queue.find({
        "priorityBand": band,
        "nextDueAt": {"$lte": now},
        "$or": [
            {"cooldownUntil": None},
            {"cooldownUntil": {"$lte": now}}
        ]
    }).sort([
        ("utilityScore", -1),
        ("nextDueAt", 1)
    ]).limit(limit).to_list(limit)
    
    return channels


async def scheduler_tick_v2(
    db,
    mtproto_client,
    process_channel_func,
    max_base: int = 20,
    max_watch: int = 20
) -> Dict[str, Any]:
    """
    Single scheduler tick - processes both bands with separate budgets.
    
    Args:
        db: MongoDB database
        mtproto_client: MTProto client instance
        process_channel_func: async function(db, client, username) -> bool
        max_base: Max channels from BASE band
        max_watch: Max channels from WATCHLIST band
    """
    results = {
        "watchlist": {"processed": 0, "errors": 0},
        "base": {"processed": 0, "errors": 0}
    }
    
    # 1. WATCHLIST LOOP (higher priority, faster refresh)
    watch_budget = WATCHLIST_UNITS_PER_HOUR // 60  # Per-minute budget
    watch_tasks = await pick_batch_v2(db, "WATCHLIST", max_watch)
    
    for task in watch_tasks:
        if watch_budget < FETCH_COST:
            break
        
        username = task.get("username")
        if not username:
            continue
        
        try:
            success = await process_channel_func(db, mtproto_client, username)
            if success:
                results["watchlist"]["processed"] += 1
                await update_next_due(db, username, "WATCHLIST", success=True)
            else:
                results["watchlist"]["errors"] += 1
                await handle_fetch_error(db, username, "Processing failed")
            
            watch_budget -= FETCH_COST
            
        except Exception as e:
            results["watchlist"]["errors"] += 1
            error_msg = str(e)
            
            # Check for FloodWait
            flood_seconds = None
            if "FLOOD_WAIT" in error_msg or "420" in error_msg:
                try:
                    flood_seconds = int(error_msg.split("_")[-1])
                except:
                    flood_seconds = 300
            
            await handle_fetch_error(db, username, error_msg, flood_seconds)
        
        # Small delay between requests
        await asyncio.sleep(0.5)
    
    # 2. BASE LOOP (lower priority, slower refresh)
    base_budget = BASE_UNITS_PER_HOUR // 60
    base_tasks = await pick_batch_v2(db, "BASE", max_base)
    
    for task in base_tasks:
        if base_budget < FETCH_COST:
            break
        
        username = task.get("username")
        if not username:
            continue
        
        try:
            success = await process_channel_func(db, mtproto_client, username)
            if success:
                results["base"]["processed"] += 1
                await update_next_due(db, username, "BASE", success=True)
            else:
                results["base"]["errors"] += 1
                await handle_fetch_error(db, username, "Processing failed")
            
            base_budget -= FETCH_COST
            
        except Exception as e:
            results["base"]["errors"] += 1
            await handle_fetch_error(db, task["username"], str(e))
        
        await asyncio.sleep(0.5)
    
    logger.info(f"Scheduler tick: WATCH {results['watchlist']}, BASE {results['base']}")
    
    return {
        "ok": True,
        "results": results,
        "timestamp": utcnow().isoformat()
    }
