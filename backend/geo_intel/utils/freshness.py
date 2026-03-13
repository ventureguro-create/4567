"""
Freshness scoring for geo events
"""
from datetime import datetime, timezone


def freshness_score(created_at: datetime) -> float:
    """
    Calculate freshness score (0.0 - 1.0) based on event age.
    
    - < 10 min: 1.0 (hot)
    - < 30 min: 0.8
    - < 1 hour: 0.6
    - < 3 hours: 0.4
    - < 24 hours: 0.2
    - older: 0.1
    """
    if not created_at:
        return 0.1
    
    now = datetime.now(timezone.utc)
    
    # Handle naive datetime
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    
    minutes = (now - created_at).total_seconds() / 60
    
    if minutes < 10:
        return 1.0
    if minutes < 30:
        return 0.8
    if minutes < 60:
        return 0.6
    if minutes < 180:
        return 0.4
    if minutes < 1440:  # 24 hours
        return 0.2
    return 0.1


def freshness_label(score: float) -> str:
    """
    Get human-readable freshness label.
    """
    if score >= 0.8:
        return "hot"
    if score >= 0.5:
        return "recent"
    if score >= 0.2:
        return "old"
    return "stale"
