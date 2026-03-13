"""Seeds Import Helper"""
from datetime import datetime, timezone
from typing import List, Dict, Any
from .discovery import normalize_username
from pymongo import UpdateOne


async def import_seeds(db, usernames: List[str]) -> Dict[str, Any]:
    """Import seed usernames as CANDIDATE channels"""
    now = datetime.now(timezone.utc)
    
    ops = []
    for u in usernames:
        username = normalize_username(u)
        if not username:
            continue
        
        ops.append(
            UpdateOne(
                {'username': username},
                {
                    '$setOnInsert': {
                        'username': username,
                        'stage': 'CANDIDATE',
                        'priority': 1,
                        'nextAllowedAt': now,
                        'createdAt': now,
                    },
                    '$set': {'updatedAt': now},
                },
                upsert=True
            )
        )
    
    if not ops:
        return {'inserted': 0}
    
    result = await db.tg_channel_states.bulk_write(ops, ordered=False)
    return {'inserted': result.upserted_count or 0}
