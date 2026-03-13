"""Ingestion Policy Configuration"""
import os
from typing import Dict, Any


def load_policy() -> Dict[str, Any]:
    """Load ingestion policy from environment"""
    return {
        'rps': _num('TG_RPS', 1),
        'floodSleepThresholdSec': _num('TG_FLOOD_SLEEP_THRESHOLD', 120),
        'hardFloodBackoffSec': _num('TG_HARD_FLOOD_BACKOFF_SEC', 21600),
        
        'safeModeWindowSec': _num('TG_SAFE_MODE_WINDOW_SEC', 600),
        'safeModeCount': _num('TG_SAFE_MODE_COUNT', 3),
        'safeModeMinWaitSec': _num('TG_SAFE_MODE_MIN_WAIT_SEC', 300),
        'safeModeDurationSec': _num('TG_SAFE_MODE_DURATION_SEC', 7200),
        
        'minSubscribers': _num('TG_MIN_SUBSCRIBERS', 1000),
        'maxInactiveDays': _num('TG_MAX_INACTIVE_DAYS', 180),
        
        'censusSampleLimit': _num('TG_CENSUS_SAMPLE_LIMIT', 30),
        'incrementalBatchLimit': _num('TG_INCREMENTAL_BATCH_LIMIT', 150),
        
        'fullInfoTtlDays': _num('TG_FULLINFO_TTL_DAYS', 14),
        'resolveCacheTtlDays': _num('TG_RESOLVE_CACHE_TTL_DAYS', 3650),
        
        # Proxy members settings
        'minMembers': _num('TG_MIN_MEMBERS', 1000),
        'proxyMembersEnabled': os.environ.get('TG_PROXY_MEMBERS_ENABLED', '1') == '1',
        'proxyMinPosts': _num('TG_PROXY_MIN_POSTS', 20),
        'proxyMinMedianViews': _num('TG_PROXY_MIN_MEDIAN_VIEWS', 350),
        'proxyMultiplier': _num('TG_PROXY_MULTIPLIER', 4.0),
        'proxyMaxRatio': _num('TG_PROXY_MAX_RATIO', 0.9),
        
        # Language & crypto gate
        'langAllow': os.environ.get('TG_LANG_ALLOW', 'ru,uk,mixed').split(','),
        'cryptoMinScore': _num('TG_CRYPTO_MIN_SCORE', 0.08),
        'langMinTexts': _num('TG_LANG_MIN_TEXTS', 10),
        
        # Proxy rule for channels where subs are unavailable
        'minEffectiveAudience': 400,
        
        # Cadence (hours)
        'qualifiedRefreshHours': 48,
        'candidateRetryHours': 24,
    }


def _num(key: str, default: float) -> float:
    """Get numeric env var with default"""
    v = os.environ.get(key)
    if v is None:
        return default
    try:
        n = float(v)
        return n if n == n else default  # NaN check
    except (ValueError, TypeError):
        return default
