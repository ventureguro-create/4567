"""Discovery Service - Extract candidates from posts"""
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Set


TME_RE = re.compile(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{4,})', re.IGNORECASE)
AT_RE = re.compile(r'@([a-zA-Z0-9_]{4,})')


def normalize_username(x: str) -> str:
    """Normalize username to lowercase without @ or t.me prefix"""
    if not x:
        return ''
    s = str(x).strip()
    s = re.sub(r'^@', '', s)
    s = re.sub(r'^https?://t\.me/', '', s, flags=re.IGNORECASE)
    s = s.split('/')[0].split('?')[0].split('#')[0]
    return s.lower()


def extract_candidates_from_post(post: Dict) -> List[str]:
    """Extract candidate usernames from a single post"""
    out = set()
    
    # Mentions pre-parsed by adapter
    if isinstance(post.get('mentions'), list):
        for m in post['mentions']:
            out.add(normalize_username(m))
    
    # Parse from text
    text = post.get('text', '')
    for m in TME_RE.findall(text):
        out.add(normalize_username(m))
    for m in AT_RE.findall(text):
        out.add(normalize_username(m))
    
    # ForwardedFrom
    fwd = post.get('forwardedFrom')
    if isinstance(fwd, dict) and fwd.get('username'):
        out.add(normalize_username(fwd['username']))
    
    # Remove self / empty
    out.discard(normalize_username(post.get('channelUsername', '')))
    out.discard('')
    
    return list(out)


def is_likely_channel_username(u: str) -> bool:
    """Check if username looks like a valid channel"""
    if not u:
        return False
    if len(u) < 4 or len(u) > 32:
        return False
    if not re.match(r'^[a-z0-9_]+$', u):
        return False
    
    # Block common false positives
    bad = {'joinchat', 'share', 'iv', 's', 'c', 'addstickers', 'proxy', 'socks'}
    if u in bad:
        return False
    
    return True


async def run_discovery_window(
    db,
    hours: int = 48,
    max_posts: int = 5000,
    max_new_candidates: int = 500
) -> Dict[str, Any]:
    """Discover new channels from recent posts"""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Pull recent posts
    cursor = db.tg_posts.find(
        {'date': {'$gte': since}},
        {'channelUsername': 1, 'text': 1, 'mentions': 1, 'forwardedFrom': 1, 'date': 1}
    ).sort('date', -1).limit(max_posts)
    
    posts = await cursor.to_list(max_posts)
    
    candidates = []
    edges = []
    
    for p in posts:
        source_username = normalize_username(p.get('channelUsername', ''))
        found = extract_candidates_from_post(p)
        
        for u in found:
            found_username = normalize_username(u)
            if not is_likely_channel_username(found_username):
                continue
            
            candidates.append(found_username)
            
            # Determine method
            fwd = p.get('forwardedFrom')
            if isinstance(fwd, dict) and normalize_username(fwd.get('username', '')) == found_username:
                method = 'FORWARD'
            else:
                method = 'MENTION'
            
            edges.append({
                'sourceUsername': source_username,
                'foundUsername': found_username,
                'method': method,
                'createdAt': datetime.now(timezone.utc),
            })
    
    # Dedupe candidates
    uniq = list(dict.fromkeys(candidates))[:max_new_candidates]
    
    # Remove blacklisted
    black_cursor = db.tg_candidate_blacklist.find(
        {'username': {'$in': uniq}},
        {'username': 1}
    )
    black = await black_cursor.to_list(len(uniq))
    black_set = {x['username'] for x in black}
    filtered = [u for u in uniq if u not in black_set]
    
    # Remove already known
    existing_cursor = db.tg_channel_states.find(
        {'username': {'$in': filtered}},
        {'username': 1}
    )
    existing = await existing_cursor.to_list(len(filtered))
    existing_set = {x['username'] for x in existing}
    to_insert = [u for u in filtered if u not in existing_set]
    
    # Enqueue as candidates
    now = datetime.now(timezone.utc)
    inserted = 0
    
    if to_insert:
        ops = [
            {
                'filter': {'username': username},
                'update': {
                    '$setOnInsert': {
                        'username': username,
                        'stage': 'CANDIDATE',
                        'priority': 2,
                        'nextAllowedAt': now,
                        'createdAt': now,
                    },
                    '$set': {'updatedAt': now},
                },
                'upsert': True,
            }
            for username in to_insert
        ]
        # Use bulk write
        from pymongo import UpdateOne
        bulk_ops = [UpdateOne(op['filter'], op['update'], upsert=op['upsert']) for op in ops]
        result = await db.tg_channel_states.bulk_write(bulk_ops, ordered=False)
        inserted = result.upserted_count or 0
    
    # Store discovery edges
    if edges:
        from pymongo import UpdateOne
        edge_ops = [
            UpdateOne(
                {
                    'foundUsername': e['foundUsername'],
                    'sourceUsername': e['sourceUsername'],
                    'method': e['method']
                },
                {'$setOnInsert': e},
                upsert=True
            )
            for e in edges
        ]
        try:
            await db.tg_discovery_edges.bulk_write(edge_ops, ordered=False)
        except Exception:
            pass  # Ignore duplicate key errors
    
    return {
        'ok': True,
        'scannedPosts': len(posts),
        'uniqCandidates': len(uniq),
        'filteredCandidates': len(filtered),
        'enqueued': inserted,
    }


async def blacklist_candidate(
    db,
    username: str,
    days: int = 30,
    reason: str = 'invalid_or_private'
) -> Dict[str, Any]:
    """Blacklist a candidate username"""
    u = normalize_username(username)
    expires_at = datetime.now(timezone.utc) + timedelta(days=days)
    
    await db.tg_candidate_blacklist.update_one(
        {'username': u},
        {
            '$set': {
                'username': u,
                'reason': reason,
                'expiresAt': expires_at,
                'updatedAt': datetime.now(timezone.utc)
            },
            '$setOnInsert': {'createdAt': datetime.now(timezone.utc)}
        },
        upsert=True
    )
    
    return {'ok': True, 'username': u, 'expiresAt': expires_at.isoformat()}
