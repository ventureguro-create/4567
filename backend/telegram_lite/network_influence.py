"""
Network Influence Layer - кто источник, кто ретранслятор
"""
import re
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional


def to_day_key(d: datetime = None) -> str:
    """Convert datetime to day key string YYYY-MM-DD"""
    if d is None:
        d = datetime.now(timezone.utc)
    if isinstance(d, str):
        d = datetime.fromisoformat(d.replace('Z', '+00:00'))
    return d.strftime('%Y-%m-%d')


def clamp01(x: float) -> float:
    """Clamp value to [0, 1]"""
    return max(0, min(1, x))


def norm_log(x: float, max_val: float = 1e6) -> float:
    """Normalize using log scale"""
    return clamp01(math.log1p(max(0, x)) / math.log1p(max_val))


def extract_mentions(text: str) -> List[str]:
    """Extract @mentions and t.me/ links"""
    if not text:
        return []
    
    usernames = set()
    
    # t.me/ links
    for match in re.findall(r'(?:https?://)?t\.me/([a-zA-Z][a-zA-Z0-9_]{3,30})', text, re.IGNORECASE):
        u = match.lower().split('/')[0].split('?')[0]
        if len(u) >= 4:
            usernames.add(u)
    
    # @mentions
    for match in re.findall(r'@([a-zA-Z][a-zA-Z0-9_]{3,30})', text):
        usernames.add(match.lower())
    
    return list(usernames)


async def ensure_network_indexes(db):
    """Create necessary indexes for network collections"""
    # Edges collection indexes
    await db.tg_network_edges.create_index(
        [('from', 1), ('to', 1), ('method', 1), ('msgId', 1)],
        unique=True
    )
    await db.tg_network_edges.create_index([('to', 1), ('date', -1)])
    await db.tg_network_edges.create_index([('from', 1), ('date', -1)])
    await db.tg_network_edges.create_index([('date', -1)])
    
    # Daily scores indexes
    await db.tg_network_scores_daily.create_index(
        [('username', 1), ('date', -1)],
        unique=True
    )
    await db.tg_network_scores_daily.create_index([('date', -1), ('networkScore', -1)])


async def upsert_edges_from_posts(
    db,
    username: str,
    posts: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Extract and store network edges from posts.
    Called during ingestion after saving posts.
    """
    if not posts:
        return {'ok': True, 'edges': 0}
    
    ops = []
    username = username.lower()
    
    for p in posts:
        text = p.get('text', '') or ''
        msg_id = p.get('messageId') or p.get('id') or 0
        
        date = p.get('date')
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                date = datetime.now(timezone.utc)
        elif not date:
            date = datetime.now(timezone.utc)
        
        # MENTIONS
        mentions = extract_mentions(text)
        for to_user in mentions:
            if not to_user or to_user == username:
                continue
            
            ops.append({
                'updateOne': {
                    'filter': {
                        'from': username,
                        'to': to_user,
                        'method': 'MENTION',
                        'msgId': msg_id,
                    },
                    'update': {
                        '$setOnInsert': {
                            'from': username,
                            'to': to_user,
                            'method': 'MENTION',
                            'weight': 1,
                            'msgId': msg_id,
                            'date': date,
                            'evidence': {'textSnippet': text[:160]},
                        }
                    },
                    'upsert': True,
                }
            })
        
        # FORWARDS
        forwarded_from = p.get('forwardedFrom')
        fwd_username = None
        
        if isinstance(forwarded_from, dict):
            fwd_username = forwarded_from.get('username')
        elif isinstance(forwarded_from, str):
            fwd_username = forwarded_from
        
        if fwd_username:
            fwd_username = fwd_username.lower().replace('@', '')
            if fwd_username != username:
                weight = max(1, p.get('forwards', 1) or 1)
                
                ops.append({
                    'updateOne': {
                        'filter': {
                            'from': username,
                            'to': fwd_username,
                            'method': 'FORWARD',
                            'msgId': msg_id,
                        },
                        'update': {
                            '$setOnInsert': {
                                'from': username,
                                'to': fwd_username,
                                'method': 'FORWARD',
                                'weight': weight,
                                'msgId': msg_id,
                                'date': date,
                                'evidence': {'textSnippet': text[:160]},
                            }
                        },
                        'upsert': True,
                    }
                })
    
    if ops:
        try:
            # Convert to pymongo format
            from pymongo import UpdateOne
            mongo_ops = [
                UpdateOne(
                    op['updateOne']['filter'],
                    op['updateOne']['update'],
                    upsert=op['updateOne'].get('upsert', False)
                )
                for op in ops
            ]
            await db.tg_network_edges.bulk_write(mongo_ops, ordered=False)
        except Exception as e:
            # Ignore duplicate key errors
            pass
    
    return {'ok': True, 'edges': len(ops)}


async def build_network_scores_daily(db, days: int = 30) -> Dict[str, Any]:
    """
    Build daily network scores for all channels.
    Calculates sourceScore, amplifierScore, networkScore, and role.
    """
    window_days = min(90, max(7, days))
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    date_key = to_day_key()
    
    # Aggregate inbound by (to, method)
    pipeline = [
        {'$match': {'date': {'$gte': since}}},
        {'$group': {
            '_id': {'to': '$to', 'method': '$method'},
            'w': {'$sum': '$weight'},
            'n': {'$sum': 1},
            'sources': {'$addToSet': '$from'},
        }},
        {'$project': {
            'to': '$_id.to',
            'method': '$_id.method',
            'w': 1,
            'n': 1,
            'uniqueSources': {'$size': '$sources'},
        }}
    ]
    
    rows = await db.tg_network_edges.aggregate(pipeline).to_list(10000)
    
    # Aggregate by channel
    by_to = {}
    for r in rows:
        key = r['to']
        if key not in by_to:
            by_to[key] = {
                'inboundMentions': 0,
                'inboundForwards': 0,
                'uniqueSourcesProxy': 0,
            }
        
        o = by_to[key]
        if r['method'] == 'MENTION':
            o['inboundMentions'] += r['n']
        if r['method'] == 'FORWARD':
            o['inboundForwards'] += r['w']
        o['uniqueSourcesProxy'] = max(o['uniqueSourcesProxy'], r.get('uniqueSources', 0))
    
    # Calculate scores for each channel
    from pymongo import UpdateOne
    ops = []
    
    for username, v in by_to.items():
        inbound_mentions = v['inboundMentions']
        inbound_forwards = v['inboundForwards']
        unique_sources = v['uniqueSourcesProxy']
        
        # SOURCE score: how often others reference this channel
        source_raw = (
            0.55 * norm_log(inbound_forwards, 20000) +
            0.25 * norm_log(unique_sources, 500) +
            0.20 * norm_log(inbound_mentions, 5000)
        )
        source_score = round(100 * clamp01(source_raw))
        
        # AMPLIFIER score: how much this channel references others (outbound)
        out_pipeline = [
            {'$match': {'from': username, 'date': {'$gte': since}}},
            {'$group': {'_id': '$method', 'w': {'$sum': '$weight'}, 'n': {'$sum': 1}}}
        ]
        out_rows = await db.tg_network_edges.aggregate(out_pipeline).to_list(10)
        
        out_mentions = 0
        out_forwards = 0
        for x in out_rows:
            if x['_id'] == 'MENTION':
                out_mentions = x['n']
            if x['_id'] == 'FORWARD':
                out_forwards = x['w']
        
        amp_raw = (
            0.60 * norm_log(out_forwards, 20000) +
            0.40 * norm_log(out_mentions, 5000)
        )
        amplifier_score = round(100 * clamp01(amp_raw))
        
        # PROMO detection: high outbound, low inbound
        promo = amplifier_score > 70 and source_score < 20
        
        # Combined network score
        if promo:
            network_score = round(100 * clamp01(0.3 * source_score / 100 + 0.7 * amplifier_score / 100) * 0.6)
        else:
            network_score = round(100 * clamp01(0.65 * source_score / 100 + 0.35 * amplifier_score / 100))
        
        # Determine role
        if promo:
            role = 'PROMO'
        elif source_score >= 60 and amplifier_score < 50:
            role = 'SOURCE'
        elif amplifier_score >= 60 and source_score < 50:
            role = 'AMPLIFIER'
        else:
            role = 'MIXED'
        
        ops.append(UpdateOne(
            {'username': username, 'date': date_key},
            {'$set': {
                'username': username,
                'date': date_key,
                'inboundMentions': inbound_mentions,
                'inboundForwards': inbound_forwards,
                'uniqueSources': unique_sources,
                'sourceScore': source_score,
                'amplifierScore': amplifier_score,
                'networkScore': network_score,
                'role': role,
            }},
            upsert=True
        ))
    
    if ops:
        await db.tg_network_scores_daily.bulk_write(ops, ordered=False)
    
    return {
        'ok': True,
        'days': window_days,
        'date': date_key,
        'upserted': len(ops),
    }


async def get_channel_network_edges(
    db,
    username: str,
    days: int = 30
) -> Dict[str, Any]:
    """Get inbound and outbound edges for a channel"""
    window_days = min(90, max(7, days))
    since = datetime.now(timezone.utc) - timedelta(days=window_days)
    username = username.lower()
    
    # Inbound (who references this channel)
    inbound_pipeline = [
        {'$match': {'to': username, 'date': {'$gte': since}}},
        {'$group': {
            '_id': {'from': '$from', 'method': '$method'},
            'n': {'$sum': 1},
            'w': {'$sum': '$weight'},
            'last': {'$max': '$date'},
        }},
        {'$sort': {'w': -1, 'n': -1}},
        {'$limit': 30},
        {'$project': {
            'from': '$_id.from',
            'method': '$_id.method',
            'count': '$n',
            'weight': '$w',
            'last': 1,
            '_id': 0,
        }}
    ]
    
    inbound = await db.tg_network_edges.aggregate(inbound_pipeline).to_list(30)
    
    # Outbound (who this channel references)
    outbound_pipeline = [
        {'$match': {'from': username, 'date': {'$gte': since}}},
        {'$group': {
            '_id': {'to': '$to', 'method': '$method'},
            'n': {'$sum': 1},
            'w': {'$sum': '$weight'},
            'last': {'$max': '$date'},
        }},
        {'$sort': {'w': -1, 'n': -1}},
        {'$limit': 30},
        {'$project': {
            'to': '$_id.to',
            'method': '$_id.method',
            'count': '$n',
            'weight': '$w',
            'last': 1,
            '_id': 0,
        }}
    ]
    
    outbound = await db.tg_network_edges.aggregate(outbound_pipeline).to_list(30)
    
    # Convert datetime to ISO
    for item in inbound:
        if item.get('last'):
            item['last'] = item['last'].isoformat() if hasattr(item['last'], 'isoformat') else str(item['last'])
    for item in outbound:
        if item.get('last'):
            item['last'] = item['last'].isoformat() if hasattr(item['last'], 'isoformat') else str(item['last'])
    
    return {
        'ok': True,
        'username': username,
        'days': window_days,
        'inbound': inbound,
        'outbound': outbound,
    }


async def get_network_leaderboard(db, limit: int = 50) -> Dict[str, Any]:
    """Get top channels by network score"""
    date_key = to_day_key()
    
    items = await db.tg_network_scores_daily.find(
        {'date': date_key}
    ).sort('networkScore', -1).limit(min(200, limit)).to_list(limit)
    
    # Clean for JSON
    for item in items:
        item.pop('_id', None)
    
    return {
        'ok': True,
        'date': date_key,
        'items': items,
    }


async def get_network_stats(db) -> Dict[str, Any]:
    """Get network statistics"""
    date_key = to_day_key()
    
    # Count edges
    total_edges = await db.tg_network_edges.count_documents({})
    
    # By method
    method_counts = await db.tg_network_edges.aggregate([
        {'$group': {'_id': '$method', 'count': {'$sum': 1}}}
    ]).to_list(10)
    
    # By role today
    role_counts = await db.tg_network_scores_daily.aggregate([
        {'$match': {'date': date_key}},
        {'$group': {'_id': '$role', 'count': {'$sum': 1}}}
    ]).to_list(10)
    
    return {
        'ok': True,
        'date': date_key,
        'totalEdges': total_edges,
        'byMethod': {x['_id']: x['count'] for x in method_counts},
        'byRole': {x['_id']: x['count'] for x in role_counts},
    }
