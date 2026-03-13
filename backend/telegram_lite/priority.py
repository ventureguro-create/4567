"""Priority Computation for Top-Down Scheduling"""
from typing import Optional
from datetime import datetime, timezone


def compute_priority_from_census(
    participants_count: Optional[int],
    proxy_members: Optional[int],
    crypto_score: float,
    lang: str,
    last_post_at: Optional[datetime]
) -> int:
    """Compute priority (1=highest, 9=lowest) based on census data"""
    members = participants_count if participants_count and participants_count > 0 else (proxy_members or 0)
    
    # Base: bigger = higher priority (lower number)
    if members >= 500000:
        p = 1
    elif members >= 100000:
        p = 2
    elif members >= 20000:
        p = 3
    elif members >= 5000:
        p = 4
    else:
        p = 5
    
    # Crypto relevance: boost
    if crypto_score >= 0.20:
        p -= 1
    elif crypto_score < 0.08:
        p += 1
    
    # Lang (ru/uk/mixed are OK)
    if lang == 'mixed':
        p -= 0.25
    
    # Activity recency: more recent posts -> boost
    if last_post_at:
        now = datetime.now(timezone.utc)
        if isinstance(last_post_at, datetime):
            days = (now - last_post_at).days
        else:
            days = 30  # default if can't calculate
        
        if days <= 3:
            p -= 0.5
        elif days <= 14:
            p -= 0.25
        elif days >= 60:
            p += 0.5
    
    # Clamp to [1..9]
    return max(1, min(9, round(p)))
