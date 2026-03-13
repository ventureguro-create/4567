"""
Discovery Engine v2 - органический рост базы через mentions/forwards
"""
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set


# Crypto keywords для relevance scoring
CRYPTO_KEYWORDS = [
    "btc", "eth", "sol", "usdt", "bnb", "xrp", "ada", "dot", "matic", "ton",
    "bitcoin", "ethereum", "solana", "биткоин", "биткойн", "эфир", "эфириум",
    "крипта", "крипто", "криптовалюта", "криптовалют", "альткоин", "альт",
    "трейдинг", "трейд", "лонг", "шорт", "фьючерс", "спот",
    "token", "токен", "airdrop", "эирдроп", "ico", "ido", "defi", "дефи", "nft", "web3",
    "стейкинг", "фарминг", "пул", "своп", "swap", "dex",
    "binance", "bybit", "okx", "kucoin", "mexc", "бинанс",
    "памп", "дамп", "ликвидация", "маржа", "плечо",
    "ончейн", "onchain", "китов", "whale", "сигнал", "сигналы",
    "мем", "мемкоин", "memecoin", "shitcoin",
]

# RU/UA language markers
RU_MARKERS = [" и ", " в ", " на ", " что ", " это ", " как ", " для ", " но ", " не "]
UA_MARKERS = [" і ", " та ", " це ", " для ", " але ", " не ", " як "]


def extract_usernames(text: str) -> List[str]:
    """Extract @mentions and t.me/ links from text"""
    if not text:
        return []
    
    usernames = set()
    
    # t.me/ links
    tme_pattern = r'(?:https?://)?t\.me/([a-zA-Z][a-zA-Z0-9_]{3,30})'
    for match in re.findall(tme_pattern, text, re.IGNORECASE):
        username = match.lower().split('/')[0].split('?')[0]
        if len(username) >= 4:
            usernames.add(username)
    
    # @mentions
    at_pattern = r'@([a-zA-Z][a-zA-Z0-9_]{3,30})'
    for match in re.findall(at_pattern, text):
        username = match.lower()
        if len(username) >= 4:
            usernames.add(username)
    
    return list(usernames)


def compute_relevance_score(text: str) -> int:
    """Compute crypto relevance score (0-20)"""
    if not text:
        return 0
    
    lower = text.lower()
    hits = 0
    
    for kw in CRYPTO_KEYWORDS:
        if kw in lower:
            hits += 1
    
    return min(20, hits)


def compute_language_score(text: str) -> Dict[str, Any]:
    """Compute RU/UA language confidence"""
    if not text:
        return {"score": 0, "lang": "UNKNOWN", "cyrillicRatio": 0}
    
    lower = text.lower()
    
    # Count markers
    ru_hits = sum(1 for m in RU_MARKERS if m in lower)
    ua_hits = sum(1 for m in UA_MARKERS if m in lower)
    
    # Cyrillic ratio
    cyrillic = len(re.findall(r'[а-яА-ЯіІїЇєЄёЁ]', text))
    total = max(1, len(text))
    cyrillic_ratio = cyrillic / total
    
    # Determine language
    if cyrillic_ratio < 0.2:
        lang = "OTHER"
        score = 0
    elif ua_hits > ru_hits:
        lang = "UA"
        score = ua_hits + (3 if cyrillic_ratio > 0.4 else 1)
    else:
        lang = "RU"
        score = ru_hits + (3 if cyrillic_ratio > 0.4 else 1)
    
    return {
        "score": score,
        "lang": lang,
        "cyrillicRatio": round(cyrillic_ratio, 2),
        "ruHits": ru_hits,
        "uaHits": ua_hits,
    }


def compute_priority_score(
    relevance_score: int,
    language_score: int,
    source_utility: float = 50,
    source_type: str = "mention",
    discovered_at: datetime = None
) -> float:
    """
    Compute discovery priority score.
    Higher score = process first.
    
    Formula:
    - 40% relevance (crypto keywords)
    - 20% language (RU/UA)
    - 20% source utility (how good is the channel that mentioned this)
    - 10% source weight (forward > mention > seed)
    - 10% freshness
    """
    # Source weight
    source_weights = {"forward": 1.2, "seed": 1.5, "mention": 1.0}
    source_weight = source_weights.get(source_type, 1.0)
    
    # Freshness (1.0 = just discovered, 0.0 = 7 days ago)
    if discovered_at:
        if isinstance(discovered_at, str):
            discovered_at = datetime.fromisoformat(discovered_at.replace('Z', '+00:00'))
        age_days = (datetime.now(timezone.utc) - discovered_at).total_seconds() / 86400
        freshness = max(0, 1 - (age_days / 7))
    else:
        freshness = 1.0
    
    # Normalize scores
    rel_norm = min(1.0, relevance_score / 10)  # 10+ keywords = max
    lang_norm = min(1.0, language_score / 5)   # 5+ markers = max
    utility_norm = min(1.0, source_utility / 100)
    
    score = (
        0.40 * rel_norm +
        0.20 * lang_norm +
        0.20 * utility_norm +
        0.10 * source_weight +
        0.10 * freshness
    )
    
    return round(score * 100, 2)


async def extract_candidates_from_posts(
    db,
    username: str,
    posts: List[Dict[str, Any]],
    source_utility: float = 50
) -> Dict[str, Any]:
    """
    Extract mention/forward candidates from posts.
    Returns candidates with relevance/language scores.
    """
    candidates = []
    seen = set()
    
    for post in posts:
        text = post.get('text', '') or ''
        
        # Extract mentions
        mentions = extract_usernames(text)
        for mentioned in mentions:
            if mentioned == username or mentioned in seen:
                continue
            seen.add(mentioned)
            
            relevance = compute_relevance_score(text)
            lang = compute_language_score(text)
            
            # Filter: need minimum relevance OR language
            if relevance < 1 and lang['score'] < 2:
                continue
            
            priority = compute_priority_score(
                relevance, lang['score'], source_utility, "mention"
            )
            
            candidates.append({
                'username': mentioned,
                'source': 'mention',
                'discoveredFrom': username,
                'relevanceScore': relevance,
                'languageScore': lang['score'],
                'language': lang['lang'],
                'priorityScore': priority,
                'discoveredAt': datetime.now(timezone.utc),
                'status': 'NEW',
                'attempts': 0,
                'evidence': {
                    'textSnippet': text[:200],
                    'postDate': post.get('date'),
                }
            })
        
        # Extract forwards
        forwarded_from = post.get('forwardedFrom')
        if forwarded_from:
            fwd_username = None
            if isinstance(forwarded_from, dict):
                fwd_username = forwarded_from.get('username')
            elif isinstance(forwarded_from, str):
                fwd_username = forwarded_from
            
            if fwd_username:
                fwd_username = fwd_username.lower().replace('@', '')
                if fwd_username != username and fwd_username not in seen:
                    seen.add(fwd_username)
                    
                    relevance = compute_relevance_score(text)
                    lang = compute_language_score(text)
                    
                    if relevance >= 1 or lang['score'] >= 2:  # Lower threshold for forwards
                        priority = compute_priority_score(
                            relevance, lang['score'], source_utility, "forward"
                        )
                        
                        candidates.append({
                            'username': fwd_username,
                            'source': 'forward',
                            'discoveredFrom': username,
                            'relevanceScore': relevance,
                            'languageScore': lang['score'],
                            'language': lang['lang'],
                            'priorityScore': priority,
                            'discoveredAt': datetime.now(timezone.utc),
                            'status': 'NEW',
                            'attempts': 0,
                            'evidence': {
                                'textSnippet': text[:200],
                                'postDate': post.get('date'),
                            }
                        })
    
    return {
        'ok': True,
        'sourceUsername': username,
        'candidatesFound': len(candidates),
        'candidates': candidates,
    }


async def save_candidates_to_queue(
    db,
    candidates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Save candidates to tg_candidate_queue (upsert)"""
    saved = 0
    duplicates = 0
    
    for c in candidates:
        try:
            result = await db.tg_candidate_queue.update_one(
                {'username': c['username']},
                {
                    '$setOnInsert': c,
                },
                upsert=True
            )
            if result.upserted_id:
                saved += 1
            else:
                duplicates += 1
        except Exception as e:
            pass  # Duplicate or error
    
    return {
        'ok': True,
        'saved': saved,
        'duplicates': duplicates,
    }


async def promote_candidates_to_ingestion(
    db,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Promote top N candidates (by priorityScore) to ingestion queue.
    """
    # Get top candidates
    cursor = db.tg_candidate_queue.find(
        {'status': 'NEW'}
    ).sort('priorityScore', -1).limit(min(50, max(1, limit)))
    
    candidates = await cursor.to_list(limit)
    
    promoted = 0
    now = datetime.now(timezone.utc)
    
    for c in candidates:
        username = c.get('username')
        if not username:
            continue
        
        # Check if already in ingestion queue
        existing = await db.tg_channel_states.find_one({'username': username})
        if existing:
            # Mark as already processed
            await db.tg_candidate_queue.update_one(
                {'username': username},
                {'$set': {'status': 'ALREADY_EXISTS'}}
            )
            continue
        
        # Add to channel states for ingestion
        await db.tg_channel_states.update_one(
            {'username': username},
            {
                '$setOnInsert': {
                    'username': username,
                    'discoveredFrom': c.get('discoveredFrom'),
                    'discoverySource': c.get('source'),
                    'priorityScore': c.get('priorityScore', 0),
                    'eligibility': {'status': 'UNKNOWN'},
                    'createdAt': now,
                },
                '$set': {
                    'nextRunAt': now,
                    'updatedAt': now,
                }
            },
            upsert=True
        )
        
        # Mark candidate as enqueued
        await db.tg_candidate_queue.update_one(
            {'username': username},
            {'$set': {'status': 'ENQUEUED', 'enqueuedAt': now}}
        )
        
        promoted += 1
    
    return {
        'ok': True,
        'promoted': promoted,
        'scanned': len(candidates),
    }


async def recalculate_candidate_priorities(db) -> Dict[str, Any]:
    """Recalculate priorities for all NEW candidates"""
    cursor = db.tg_candidate_queue.find({'status': 'NEW'})
    candidates = await cursor.to_list(1000)
    
    updated = 0
    
    for c in candidates:
        # Get source channel utility
        source = await db.tg_channel_states.find_one({'username': c.get('discoveredFrom')})
        source_utility = 50
        if source:
            # Use utility from snapshots if available
            snap = await db.tg_score_snapshots.find_one(
                {'username': source.get('username')},
                sort=[('date', -1)]
            )
            if snap:
                source_utility = snap.get('utility', 50)
        
        priority = compute_priority_score(
            c.get('relevanceScore', 0),
            c.get('languageScore', 0),
            source_utility,
            c.get('source', 'mention'),
            c.get('discoveredAt')
        )
        
        await db.tg_candidate_queue.update_one(
            {'_id': c['_id']},
            {'$set': {'priorityScore': priority}}
        )
        updated += 1
    
    return {'ok': True, 'updated': updated}


async def get_candidate_stats(db) -> Dict[str, Any]:
    """Get candidate queue statistics"""
    pipeline = [
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]
    
    by_status = await db.tg_candidate_queue.aggregate(pipeline).to_list(10)
    
    # Top by priority
    top = await db.tg_candidate_queue.find(
        {'status': 'NEW'}
    ).sort('priorityScore', -1).limit(10).to_list(10)
    
    return {
        'ok': True,
        'byStatus': {x['_id']: x['count'] for x in by_status},
        'topCandidates': [
            {
                'username': c.get('username'),
                'priorityScore': c.get('priorityScore'),
                'relevanceScore': c.get('relevanceScore'),
                'source': c.get('source'),
                'discoveredFrom': c.get('discoveredFrom'),
            }
            for c in top
        ]
    }
