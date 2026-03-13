"""Query Builder for Filter API"""
import re
from typing import Dict, Any, List, Optional


def parse_list_query(qs: Dict) -> Dict[str, Any]:
    """Parse query string parameters for list endpoint"""
    return {
        'q': str(qs.get('q', '')).strip(),
        'page': _clamp_int(qs.get('page'), 1, 100000, 1),
        'limit': _clamp_int(qs.get('limit'), 5, 200, 50),
        
        'lang': _parse_csv(qs.get('lang')),
        'tier': _parse_csv(qs.get('tier')),
        'lifecycle': _parse_csv(qs.get('lifecycle')),
        
        'minMembers': _num_or_none(qs.get('minMembers')),
        'maxMembers': _num_or_none(qs.get('maxMembers')),
        
        'minReach': _num_or_none(qs.get('minReach')),
        'maxReach': _num_or_none(qs.get('maxReach')),
        
        'minGrowth7': _num_or_none(qs.get('minGrowth7')),
        'maxGrowth7': _num_or_none(qs.get('maxGrowth7')),
        
        'minPostsPerDay': _num_or_none(qs.get('minPostsPerDay')),
        'maxPostsPerDay': _num_or_none(qs.get('maxPostsPerDay')),
        
        'maxFraud': _num_or_none(qs.get('maxFraud')),
        'minCrypto': _num_or_none(qs.get('minCrypto')),
        
        'sort': str(qs.get('sort', 'utility')),
        'order': str(qs.get('order', 'desc')),
    }


def build_mongo_filter(parsed: Dict) -> Dict:
    """Build MongoDB filter from parsed query"""
    flt = {}
    
    # Search
    if parsed['q']:
        escaped = _escape_regex(parsed['q'])
        flt['$or'] = [
            {'username': {'$regex': escaped, '$options': 'i'}},
            {'title': {'$regex': escaped, '$options': 'i'}},
        ]
    
    # Lang
    if parsed['lang']:
        flt['lang'] = {'$in': parsed['lang']}
    
    # Tier
    if parsed['tier']:
        flt['utilityTier'] = {'$in': parsed['tier']}
    
    # Lifecycle
    if parsed['lifecycle']:
        flt['lifecycle'] = {'$in': parsed['lifecycle']}
    
    # Members
    if parsed['minMembers'] is not None or parsed['maxMembers'] is not None:
        flt['members'] = {}
        if parsed['minMembers'] is not None:
            flt['members']['$gte'] = parsed['minMembers']
        if parsed['maxMembers'] is not None:
            flt['members']['$lte'] = parsed['maxMembers']
    
    # Reach
    if parsed['minReach'] is not None or parsed['maxReach'] is not None:
        flt['avgReach'] = {}
        if parsed['minReach'] is not None:
            flt['avgReach']['$gte'] = parsed['minReach']
        if parsed['maxReach'] is not None:
            flt['avgReach']['$lte'] = parsed['maxReach']
    
    # Growth7
    if parsed['minGrowth7'] is not None or parsed['maxGrowth7'] is not None:
        flt['growth7'] = {}
        if parsed['minGrowth7'] is not None:
            flt['growth7']['$gte'] = parsed['minGrowth7']
        if parsed['maxGrowth7'] is not None:
            flt['growth7']['$lte'] = parsed['maxGrowth7']
    
    # Posts per day
    if parsed['minPostsPerDay'] is not None or parsed['maxPostsPerDay'] is not None:
        flt['postsPerDay30'] = {}
        if parsed['minPostsPerDay'] is not None:
            flt['postsPerDay30']['$gte'] = parsed['minPostsPerDay']
        if parsed['maxPostsPerDay'] is not None:
            flt['postsPerDay30']['$lte'] = parsed['maxPostsPerDay']
    
    # Fraud
    if parsed['maxFraud'] is not None:
        flt['fraudRisk'] = {'$lte': parsed['maxFraud']}
    
    # Crypto relevance
    if parsed['minCrypto'] is not None:
        flt['cryptoRelevanceScore'] = {'$gte': parsed['minCrypto']}
    
    # Only qualified channels
    flt['utilityScore'] = {'$exists': True}
    
    return flt


def build_mongo_sort(parsed: Dict) -> List[tuple]:
    """Build MongoDB sort from parsed query"""
    direction = 1 if parsed['order'] == 'asc' else -1
    
    sort_map = {
        'growth7': [('growth7', direction), ('utilityScore', -1)],
        'reach': [('avgReach', direction), ('utilityScore', -1)],
        'members': [('members', direction), ('utilityScore', -1)],
        'fraud': [('fraudRisk', direction), ('utilityScore', -1)],
        'fresh': [('lastPostAt', direction), ('utilityScore', -1)],
        'utility': [('utilityScore', direction), ('fraudRisk', 1)],
    }
    
    return sort_map.get(parsed['sort'], sort_map['utility'])


def _parse_csv(x) -> List[str]:
    if not x:
        return []
    return [s.strip() for s in str(x).split(',') if s.strip()]


def _num_or_none(x) -> Optional[float]:
    if x is None or x == '':
        return None
    try:
        n = float(x)
        return n if n == n else None  # NaN check
    except (ValueError, TypeError):
        return None


def _clamp_int(x, lo: int, hi: int, default: int) -> int:
    try:
        n = int(x)
        return max(lo, min(hi, n))
    except (ValueError, TypeError):
        return default


def _escape_regex(s: str) -> str:
    return re.sub(r'[.*+?^${}()|[\]\\]', r'\\\g<0>', str(s))
