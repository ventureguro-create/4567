"""Safe Mode & Flood Event Handling"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional


async def record_flood_event(db, wait_sec: int, method: str = 'unknown', username: str = None):
    """Record a flood event for monitoring"""
    await db.tg_flood_events.insert_one({
        'ts': datetime.now(timezone.utc),
        'waitSec': wait_sec,
        'method': method,
        'username': username,
    })


async def is_safe_mode_active(db, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Check if safe mode is currently active"""
    doc = await db.tg_runtime_state.find_one({'_id': 'safe_mode'})
    if not doc:
        return {'active': False}
    
    until = doc.get('until')
    if until and until > datetime.now(timezone.utc):
        return {'active': True, 'until': until}
    
    return {'active': False}


async def maybe_enter_safe_mode(db, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Check if we should enter safe mode based on recent flood events"""
    since = datetime.now(timezone.utc) - timedelta(seconds=policy['safeModeWindowSec'])
    
    count = await db.tg_flood_events.count_documents({
        'ts': {'$gte': since},
        'waitSec': {'$gte': policy['safeModeMinWaitSec']},
    })
    
    if count >= policy['safeModeCount']:
        until = datetime.now(timezone.utc) + timedelta(seconds=policy['safeModeDurationSec'])
        await db.tg_runtime_state.update_one(
            {'_id': 'safe_mode'},
            {'$set': {
                'until': until,
                'activatedAt': datetime.now(timezone.utc),
                'reason': 'FLOOD_CLUSTER',
                'count': count
            }},
            upsert=True
        )
        return {'entered': True, 'until': until}
    
    return {'entered': False}
