"""Members Proxy Estimation"""
from typing import List, Dict, Any, Optional
import statistics


def estimate_proxy_members(
    posts: List[Dict],
    participants_count: Optional[int],
    opts: Dict[str, Any]
) -> Dict[str, Any]:
    """Estimate channel members when Telegram doesn't provide participantsCount"""
    min_posts = int(opts.get('minPosts', 20))
    min_median_views = float(opts.get('minMedianViews', 350))
    multiplier = float(opts.get('multiplier', 4.0))
    max_ratio = float(opts.get('maxRatio', 0.9))
    
    # If we have real members count, use it
    if isinstance(participants_count, (int, float)) and participants_count > 0:
        return {
            'hasRealMembers': True,
            'members': int(participants_count),
            'proxyMembers': int(participants_count),
            'proxyUsed': False,
            'confidence': 1.0,
            'reason': 'real_members',
        }
    
    # Not enough posts for estimation
    if not posts or len(posts) < min_posts:
        return {
            'hasRealMembers': False,
            'members': None,
            'proxyMembers': None,
            'proxyUsed': False,
            'confidence': 0,
            'reason': 'insufficient_posts',
        }
    
    # Extract views
    views = [int(p.get('views', 0)) for p in posts if p.get('views', 0) > 0]
    
    if len(views) < max(10, int(min_posts * 0.5)):
        return {
            'hasRealMembers': False,
            'members': None,
            'proxyMembers': None,
            'proxyUsed': False,
            'confidence': 0.2,
            'reason': 'insufficient_views',
        }
    
    med = statistics.median(views)
    
    if med < min_median_views:
        return {
            'hasRealMembers': False,
            'members': None,
            'proxyMembers': round(med * multiplier),
            'proxyUsed': True,
            'confidence': 0.4,
            'reason': 'low_median_views',
            'medianViews': med,
        }
    
    # Proxy estimation
    proxy = round(med * multiplier)
    
    # Sanity check: if proxy too close to median views -> suspicious
    ratio = med / max(1, proxy)
    suspicious = ratio > max_ratio
    
    return {
        'hasRealMembers': False,
        'members': None,
        'proxyMembers': proxy,
        'proxyUsed': True,
        'confidence': 0.45 if suspicious else 0.7,
        'reason': 'suspicious_view_ratio' if suspicious else 'proxy_from_views',
        'medianViews': med,
        'viewToProxyRatio': ratio,
    }
