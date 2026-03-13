"""
Ingestion Queue Module - пакетная обработка каналов
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from .policy import load_policy
from .safe_mode import is_safe_mode_active
from .eligibility import (
    compute_eligibility, 
    EligibilityStatus, 
    compute_refresh_interval_hours
)


async def get_queue_candidates(
    db,
    limit: int = 30,
    policy: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Получить каналы для обработки из очереди
    
    Приоритет:
    1. Каналы без eligibility (новые)
    2. ELIGIBLE каналы с nextRunAt <= now
    3. По priority (1 = высший)
    """
    if policy is None:
        policy = load_policy()
    
    # Check safe mode
    safe = await is_safe_mode_active(db, policy)
    if safe['active']:
        return []
    
    now = datetime.now(timezone.utc)
    
    # Query: eligible channels ready for refresh OR new channels
    cursor = db.tg_channel_states.find(
        {
            '$or': [
                # New channels without eligibility
                {'eligibility': {'$exists': False}},
                # Eligible channels ready for refresh
                {
                    'eligibility.status': EligibilityStatus.ELIGIBLE,
                    '$or': [
                        {'nextRunAt': {'$lte': now}},
                        {'nextRunAt': {'$exists': False}},
                    ]
                },
                # Pending channels (need more data)
                {
                    'eligibility.status': EligibilityStatus.PENDING,
                    '$or': [
                        {'nextRunAt': {'$lte': now}},
                        {'nextRunAt': {'$exists': False}},
                    ]
                },
            ],
            # Exclude cooldown
            '$and': [
                {'$or': [
                    {'cooldownUntil': {'$exists': False}},
                    {'cooldownUntil': {'$lte': now}},
                ]}
            ]
        },
        {
            'username': 1,
            'priority': 1,
            'eligibility': 1,
            'participantsCount': 1,
            'nextRunAt': 1,
            'lastRefreshAt': 1,
        }
    ).sort([
        ('priority', 1),
        ('lastRefreshAt', 1),
        ('nextRunAt', 1),
    ]).limit(limit)
    
    return await cursor.to_list(limit)


async def process_ingestion_result(
    db,
    username: str,
    result: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Обработать результат ingestion и обновить состояние канала
    """
    if policy is None:
        policy = load_policy()
    
    now = datetime.now(timezone.utc)
    
    # Get current state
    channel_state = await db.tg_channel_states.find_one({'username': username})
    if not channel_state:
        channel_state = {'username': username}
    
    # Update with result data
    if result.get('ok'):
        update_data = {
            'lastIngestionAt': now,
            'lastIngestionOk': True,
            'updatedAt': now,
        }
        
        # Update members if available
        if result.get('participantsCount'):
            update_data['participantsCount'] = result['participantsCount']
            channel_state['participantsCount'] = result['participantsCount']
        
        # Update last post date if available
        if result.get('lastPostAt'):
            update_data['lastPostAt'] = result['lastPostAt']
            channel_state['lastPostAt'] = result['lastPostAt']
        
        # Compute eligibility
        eligibility = compute_eligibility(channel_state, policy)
        update_data['eligibility'] = {
            'status': eligibility['status'],
            'reasons': eligibility['reasons'],
            'details': eligibility['details'],
            'evaluatedAt': eligibility['evaluatedAt'],
        }
        
        # Schedule next refresh based on eligibility
        if eligibility['status'] == EligibilityStatus.ELIGIBLE:
            hours = compute_refresh_interval_hours(channel_state)
            update_data['nextRunAt'] = now + timedelta(hours=hours)
            update_data['refreshIntervalHours'] = hours
        elif eligibility['status'] == EligibilityStatus.EXCLUDED:
            # Excluded channels: check again in 7 days
            update_data['nextRunAt'] = now + timedelta(days=7)
        else:
            # Pending: retry in 24h
            update_data['nextRunAt'] = now + timedelta(hours=24)
        
        await db.tg_channel_states.update_one(
            {'username': username},
            {'$set': update_data},
            upsert=True
        )
        
        return {
            'ok': True,
            'username': username,
            'eligibility': eligibility['status'],
            'nextRunAt': update_data['nextRunAt'].isoformat(),
        }
    else:
        # Ingestion failed
        error_type = result.get('error', 'UNKNOWN')
        
        update_data = {
            'lastIngestionAt': now,
            'lastIngestionOk': False,
            'lastError': {
                'type': error_type,
                'message': result.get('message', ''),
                'at': now,
            },
            'updatedAt': now,
        }
        
        # Set cooldown based on error type
        if error_type == 'FLOOD_WAIT':
            wait_seconds = result.get('seconds', 300)
            update_data['cooldownUntil'] = now + timedelta(seconds=wait_seconds + 60)
        elif error_type == 'PRIVATE':
            # Private channel: mark as excluded
            update_data['eligibility'] = {
                'status': EligibilityStatus.EXCLUDED,
                'reasons': ['PRIVATE'],
                'details': {},
                'evaluatedAt': now,
            }
            update_data['nextRunAt'] = now + timedelta(days=30)
        elif error_type == 'NOT_FOUND':
            # Username doesn't exist
            update_data['eligibility'] = {
                'status': EligibilityStatus.EXCLUDED,
                'reasons': ['NOT_FOUND'],
                'details': {},
                'evaluatedAt': now,
            }
            update_data['nextRunAt'] = now + timedelta(days=30)
        else:
            # Retry in 6 hours
            update_data['nextRunAt'] = now + timedelta(hours=6)
        
        await db.tg_channel_states.update_one(
            {'username': username},
            {'$set': update_data},
            upsert=True
        )
        
        return {
            'ok': False,
            'username': username,
            'error': error_type,
        }


async def get_queue_stats(db) -> Dict[str, Any]:
    """
    Получить статистику очереди
    """
    now = datetime.now(timezone.utc)
    
    # Aggregate by eligibility status
    eligibility_stats = await db.tg_channel_states.aggregate([
        {
            '$group': {
                '_id': '$eligibility.status',
                'count': {'$sum': 1},
            }
        }
    ]).to_list(10)
    
    # Count ready for processing
    ready_count = await db.tg_channel_states.count_documents({
        '$or': [
            {'eligibility': {'$exists': False}},
            {
                'eligibility.status': {'$in': [EligibilityStatus.ELIGIBLE, EligibilityStatus.PENDING]},
                '$or': [
                    {'nextRunAt': {'$lte': now}},
                    {'nextRunAt': {'$exists': False}},
                ]
            }
        ],
        '$and': [
            {'$or': [
                {'cooldownUntil': {'$exists': False}},
                {'cooldownUntil': {'$lte': now}},
            ]}
        ]
    })
    
    # Count in cooldown
    cooldown_count = await db.tg_channel_states.count_documents({
        'cooldownUntil': {'$gt': now}
    })
    
    return {
        'ok': True,
        'eligibility': {s['_id'] or 'UNKNOWN': s['count'] for s in eligibility_stats},
        'readyForProcessing': ready_count,
        'inCooldown': cooldown_count,
        'timestamp': now.isoformat(),
    }
