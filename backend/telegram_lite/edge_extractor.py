"""
Edge Events Extractor - Extract @mentions and t.me links from posts
"""
import re
import logging
from datetime import datetime
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def utcnow():
    return datetime.utcnow()


def extract_mentions_from_text(text: str) -> List[str]:
    """Extract @username mentions from text"""
    if not text:
        return []
    
    # @username pattern
    mentions = re.findall(r'@(\w{5,32})', text)
    
    # t.me/username pattern
    links = re.findall(r't\.me/(\w{5,32})', text)
    
    # Combine and dedupe, lowercase
    all_mentions = set(m.lower() for m in mentions + links)
    
    return list(all_mentions)


async def extract_edges_from_posts(db, username: str) -> int:
    """
    Extract edges from posts for a channel.
    Creates edge_events collection entries.
    Returns count of edges created.
    """
    username = username.lower()
    
    # Get posts
    posts = await db.tg_posts.find({"username": username}).to_list(100)
    
    if not posts:
        return 0
    
    edges_created = 0
    
    for post in posts:
        text = post.get("text", "")
        mentions = extract_mentions_from_text(text)
        
        # Skip self-mentions
        mentions = [m for m in mentions if m != username]
        
        if not mentions:
            continue
        
        post_date = post.get("date", utcnow())
        msg_id = post.get("messageId")
        
        for target in mentions:
            # Upsert edge event
            edge_doc = {
                "source": username,
                "target": target,
                "postId": msg_id,
                "date": post_date,
                "updatedAt": utcnow(),
            }
            
            result = await db.tg_edge_events.update_one(
                {"source": username, "target": target, "postId": msg_id},
                {"$set": edge_doc},
                upsert=True
            )
            
            if result.upserted_id or result.modified_count:
                edges_created += 1
    
    logger.info(f"Extracted {edges_created} edges for {username}")
    return edges_created


async def ensure_edge_indexes(db):
    """Create indexes for edge_events collection"""
    try:
        await db.tg_edge_events.create_index(
            [("source", 1), ("target", 1), ("postId", 1)],
            unique=True,
            background=True
        )
        await db.tg_edge_events.create_index([("source", 1)], background=True)
        await db.tg_edge_events.create_index([("target", 1)], background=True)
        logger.info("Edge events indexes created")
    except Exception as e:
        logger.warning(f"Edge index creation warning: {e}")
