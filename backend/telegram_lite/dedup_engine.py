"""
Anti-Duplication Engine - Feed Clustering
Detects duplicate posts across channels and clusters them.
"""
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def normalize_text(text: str) -> str:
    """Normalize text for deduplication"""
    if not text:
        return ""
    # Lowercase
    text = text.lower()
    # Remove URLs
    text = re.sub(r"http\S+", "", text)
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text)
    # Remove special chars except letters/numbers
    text = re.sub(r"[^\w\s]", "", text)
    return text.strip()


def get_text_hash(text: str) -> str:
    """Get SHA256 hash of normalized text"""
    normalized = normalize_text(text)
    if len(normalized) < 20:  # Too short to dedupe
        return ""
    return hashlib.sha256(normalized.encode()).hexdigest()


async def find_duplicates(
    db,
    posts: List[Dict[str, Any]],
    window_hours: int = 6
) -> Dict[str, Dict]:
    """
    Find duplicate posts in a list.
    
    Returns dict mapping messageKey -> cluster info
    """
    # Group posts by text hash
    hash_groups = {}
    
    for post in posts:
        text = post.get("text", "")
        text_hash = get_text_hash(text)
        
        if not text_hash:
            continue
        
        post_date = post.get("date")
        if isinstance(post_date, str):
            try:
                post_date = datetime.fromisoformat(post_date.replace("Z", "+00:00")).replace(tzinfo=None)
            except:
                post_date = datetime.utcnow()
        
        key = f"{post.get('username')}:{post.get('messageId')}"
        
        if text_hash not in hash_groups:
            hash_groups[text_hash] = []
        
        hash_groups[text_hash].append({
            "key": key,
            "username": post.get("username"),
            "messageId": post.get("messageId"),
            "date": post_date,
            "views": post.get("views", 0),
        })
    
    # Build cluster map
    cluster_map = {}
    
    for text_hash, group in hash_groups.items():
        if len(group) < 2:
            continue
        
        # Sort by date (oldest first = original)
        group.sort(key=lambda x: x["date"])
        
        # Check if within time window
        oldest = group[0]["date"]
        newest = group[-1]["date"]
        
        if (newest - oldest).total_seconds() / 3600 > window_hours:
            # Posts too far apart - not duplicates
            continue
        
        # First post is the "main", rest are duplicates
        main_post = group[0]
        duplicates = group[1:]
        
        # Create cluster entry for main post
        cluster_map[main_post["key"]] = {
            "isCluster": True,
            "isMain": True,
            "clusterSize": len(group),
            "alsoPostedBy": [d["username"] for d in duplicates],
            "textHash": text_hash[:16]
        }
        
        # Create entries for duplicates
        for dup in duplicates:
            cluster_map[dup["key"]] = {
                "isCluster": True,
                "isMain": False,
                "clusterSize": len(group),
                "mainPost": main_post["key"],
                "textHash": text_hash[:16]
            }
    
    return cluster_map


async def enrich_posts_with_clusters(
    db,
    posts: List[Dict[str, Any]],
    hide_duplicates: bool = True
) -> List[Dict[str, Any]]:
    """
    Enrich posts with cluster info and optionally hide duplicates.
    
    If hide_duplicates=True, only main posts are returned.
    """
    cluster_map = await find_duplicates(db, posts)
    
    result = []
    for post in posts:
        key = f"{post.get('username')}:{post.get('messageId')}"
        cluster_info = cluster_map.get(key, {})
        
        # Skip duplicates if hiding
        if hide_duplicates and cluster_info.get("isCluster") and not cluster_info.get("isMain"):
            continue
        
        # Add cluster info to post
        enriched = {**post}
        if cluster_info:
            enriched["isCluster"] = cluster_info.get("isCluster", False)
            enriched["clusterSize"] = cluster_info.get("clusterSize", 1)
            enriched["alsoPostedBy"] = cluster_info.get("alsoPostedBy", [])
        else:
            enriched["isCluster"] = False
            enriched["clusterSize"] = 1
            enriched["alsoPostedBy"] = []
        
        result.append(enriched)
    
    return result


async def ensure_cluster_indexes(db):
    """Create indexes for clustering"""
    try:
        await db.tg_posts.create_index([("textHash", 1)])
        logger.info("Cluster index created")
    except Exception as e:
        logger.warning(f"Cluster index warning: {e}")
