"""
Eligibility Rules Module - отсеиваем каналы по критериям
P0 Rules:
- members >= 1000 (если доступно)
- lastPostAt <= 180 дней
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from .policy import load_policy


class EligibilityStatus:
    ELIGIBLE = "ELIGIBLE"
    EXCLUDED = "EXCLUDED"
    PENDING = "PENDING"  # Недостаточно данных для оценки


class EligibilityReasons:
    LOW_MEMBERS = "LOW_MEMBERS"           # < 1000 подписчиков
    INACTIVE_180D = "INACTIVE_180D"       # Нет постов > 180 дней
    NO_USERNAME = "NO_USERNAME"           # Нет username
    PRIVATE = "PRIVATE"                   # Приватный канал
    RESTRICTED = "RESTRICTED"             # Ограниченный канал
    DELETED = "DELETED"                   # Удалённый канал
    NO_DATA = "NO_DATA"                   # Нет данных для оценки
    MANUAL_EXCLUDE = "MANUAL_EXCLUDE"     # Исключен вручную
    LOW_CRYPTO_SCORE = "LOW_CRYPTO_SCORE" # Низкая крипто-релевантность
    FETCH_ERROR = "FETCH_ERROR"           # Ошибка при fetch


def compute_eligibility(
    channel_state: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Вычислить eligibility статус канала
    
    Returns:
        {
            "status": "ELIGIBLE" | "EXCLUDED" | "PENDING",
            "reasons": ["LOW_MEMBERS", ...],
            "details": {...}
        }
    """
    if policy is None:
        policy = load_policy()
    
    min_subscribers = policy.get('minSubscribers', 1000)
    max_inactive_days = policy.get('maxInactiveDays', 180)
    min_crypto_score = policy.get('cryptoMinScore', 0.08)
    
    reasons = []
    details = {}
    
    # 1. Check username
    username = channel_state.get('username')
    if not username:
        reasons.append(EligibilityReasons.NO_USERNAME)
    
    # 2. Check members
    members = channel_state.get('participantsCount') or channel_state.get('proxyMembers')
    if members is not None:
        details['members'] = members
        if members < min_subscribers:
            reasons.append(EligibilityReasons.LOW_MEMBERS)
            details['minRequired'] = min_subscribers
    
    # 3. Check last post date (activity)
    last_post_at = channel_state.get('lastPostAt')
    if last_post_at:
        if isinstance(last_post_at, str):
            try:
                last_post_at = datetime.fromisoformat(last_post_at.replace('Z', '+00:00'))
            except:
                last_post_at = None
        
        if last_post_at:
            now = datetime.now(timezone.utc)
            days_since_post = (now - last_post_at).days
            details['daysSinceLastPost'] = days_since_post
            
            if days_since_post > max_inactive_days:
                reasons.append(EligibilityReasons.INACTIVE_180D)
                details['maxInactiveDays'] = max_inactive_days
    
    # 4. Check crypto relevance score (если есть)
    crypto_score = channel_state.get('cryptoRelevanceScore')
    if crypto_score is not None:
        details['cryptoScore'] = crypto_score
        if crypto_score < min_crypto_score:
            reasons.append(EligibilityReasons.LOW_CRYPTO_SCORE)
    
    # 5. Check if private
    if channel_state.get('isPrivate'):
        reasons.append(EligibilityReasons.PRIVATE)
    
    # 6. Check if restricted
    if channel_state.get('isRestricted'):
        reasons.append(EligibilityReasons.RESTRICTED)
    
    # 7. Check if deleted
    if channel_state.get('isDeleted'):
        reasons.append(EligibilityReasons.DELETED)
    
    # 8. Check fetch errors
    last_error = channel_state.get('lastError', {})
    if last_error.get('type') in ('NOT_FOUND', 'PRIVATE', 'INVALID'):
        reasons.append(EligibilityReasons.FETCH_ERROR)
    
    # Determine status
    if reasons:
        status = EligibilityStatus.EXCLUDED
    elif members is None and last_post_at is None:
        status = EligibilityStatus.PENDING
        reasons.append(EligibilityReasons.NO_DATA)
    else:
        status = EligibilityStatus.ELIGIBLE
    
    return {
        'status': status,
        'reasons': reasons,
        'details': details,
        'evaluatedAt': datetime.now(timezone.utc)
    }


async def evaluate_and_save_eligibility(
    db,
    username: str,
    channel_state: Optional[Dict[str, Any]] = None,
    policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Оценить eligibility и сохранить в базу
    """
    if channel_state is None:
        channel_state = await db.tg_channel_states.find_one({'username': username})
        if not channel_state:
            return {'ok': False, 'error': 'Channel not found'}
    
    eligibility = compute_eligibility(channel_state, policy)
    
    # Update channel state with eligibility
    await db.tg_channel_states.update_one(
        {'username': username},
        {
            '$set': {
                'eligibility': {
                    'status': eligibility['status'],
                    'reasons': eligibility['reasons'],
                    'details': eligibility['details'],
                    'evaluatedAt': eligibility['evaluatedAt'],
                },
                'updatedAt': datetime.now(timezone.utc),
            }
        }
    )
    
    return {'ok': True, 'username': username, 'eligibility': eligibility}


async def batch_evaluate_eligibility(
    db,
    limit: int = 100,
    policy: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Пакетная оценка eligibility для каналов без оценки
    """
    if policy is None:
        policy = load_policy()
    
    # Find channels without eligibility or with old evaluation
    cursor = db.tg_channel_states.find(
        {
            '$or': [
                {'eligibility': {'$exists': False}},
                {'eligibility.status': {'$exists': False}},
            ]
        }
    ).limit(limit)
    
    channels = await cursor.to_list(limit)
    
    eligible_count = 0
    excluded_count = 0
    pending_count = 0
    
    for ch in channels:
        eligibility = compute_eligibility(ch, policy)
        
        await db.tg_channel_states.update_one(
            {'username': ch['username']},
            {
                '$set': {
                    'eligibility': {
                        'status': eligibility['status'],
                        'reasons': eligibility['reasons'],
                        'details': eligibility['details'],
                        'evaluatedAt': eligibility['evaluatedAt'],
                    },
                    'updatedAt': datetime.now(timezone.utc),
                }
            }
        )
        
        if eligibility['status'] == EligibilityStatus.ELIGIBLE:
            eligible_count += 1
        elif eligibility['status'] == EligibilityStatus.EXCLUDED:
            excluded_count += 1
        else:
            pending_count += 1
    
    return {
        'ok': True,
        'processed': len(channels),
        'eligible': eligible_count,
        'excluded': excluded_count,
        'pending': pending_count,
    }


def compute_refresh_interval_hours(channel_state: Dict[str, Any]) -> int:
    """
    Вычислить интервал обновления по размеру канала
    - members > 100k → 24h
    - 10k–100k → 48h
    - 1k–10k → 72h
    """
    members = channel_state.get('participantsCount') or channel_state.get('proxyMembers') or 0
    
    if members > 100_000:
        return 24
    elif members > 10_000:
        return 48
    else:
        return 72


async def schedule_next_refresh(
    db,
    username: str,
    channel_state: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Запланировать следующее обновление канала
    """
    if channel_state is None:
        channel_state = await db.tg_channel_states.find_one({'username': username})
        if not channel_state:
            return {'ok': False, 'error': 'Channel not found'}
    
    hours = compute_refresh_interval_hours(channel_state)
    next_run_at = datetime.now(timezone.utc) + timedelta(hours=hours)
    
    await db.tg_channel_states.update_one(
        {'username': username},
        {
            '$set': {
                'nextRunAt': next_run_at,
                'refreshIntervalHours': hours,
                'lastRefreshAt': datetime.now(timezone.utc),
                'updatedAt': datetime.now(timezone.utc),
            }
        }
    )
    
    return {
        'ok': True,
        'username': username,
        'nextRunAt': next_run_at.isoformat(),
        'intervalHours': hours,
    }
