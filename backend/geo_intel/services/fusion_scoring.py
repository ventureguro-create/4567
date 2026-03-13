"""
Fusion Scoring
Computes confidence and status for fused events
"""
from datetime import datetime, timezone


def compute_fusion_confidence(source_count: int, channel_count: int, freshness_minutes: float) -> float:
    """
    Compute confidence score for fused event.
    
    Args:
        source_count: Number of source messages
        channel_count: Number of unique channels
        freshness_minutes: Age in minutes
    
    Returns:
        Confidence score 0.0 - 1.0
    """
    # More sources = higher confidence
    source_score = min(source_count / 5, 1.0)
    
    # More channels = higher cross-validation
    channel_score = min(channel_count / 3, 1.0)
    
    # Fresher = higher confidence
    if freshness_minutes < 10:
        freshness_score = 1.0
    elif freshness_minutes < 30:
        freshness_score = 0.7
    elif freshness_minutes < 60:
        freshness_score = 0.5
    else:
        freshness_score = 0.3
    
    confidence = (
        source_score * 0.45 +
        channel_score * 0.35 +
        freshness_score * 0.20
    )
    
    return round(min(confidence, 1.0), 2)


def compute_status(source_count: int, confidence: float, last_seen_at: datetime) -> str:
    """
    Compute lifecycle status for fused event.
    
    Statuses:
    - NEW: Single source, low confidence
    - CONFIRMED: Multiple sources or high confidence
    - ACTIVE: Confirmed but aging
    - DECAYING: Old, losing relevance
    - EXPIRED: Too old, should not show
    """
    now = datetime.now(timezone.utc)
    
    # Handle naive datetime
    if last_seen_at.tzinfo is None:
        last_seen_at = last_seen_at.replace(tzinfo=timezone.utc)
    
    age_minutes = (now - last_seen_at).total_seconds() / 60
    
    # Expired after 3 hours
    if age_minutes > 180:
        return "EXPIRED"
    
    # Decaying after 1 hour
    if age_minutes > 60:
        return "DECAYING"
    
    # Active if moderately old
    if age_minutes > 30:
        if source_count >= 2 or confidence >= 0.6:
            return "ACTIVE"
        return "DECAYING"
    
    # Confirmed if multiple sources or high confidence
    if source_count >= 2 or confidence >= 0.75:
        return "CONFIRMED"
    
    return "NEW"
