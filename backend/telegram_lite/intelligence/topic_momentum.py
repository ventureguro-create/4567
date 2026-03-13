"""
Topic Momentum Engine - Detect trending topics with velocity
"""
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class TopicRepository:
    """Repository for topic aggregation queries"""
    
    def __init__(self, db):
        self.db = db
    
    async def count_mentions(self, topic: str, since_hours: int) -> int:
        """Count mentions of topic in time window"""
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        since_str = since.isoformat()
        
        return await self.db.tg_posts.count_documents({
            "date": {"$gte": since_str},
            "extractedTopics": topic
        })
    
    async def aggregate_topics(self, since_hours: int, limit: int = 50) -> List[Dict]:
        """Get top topics by frequency in time window"""
        since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        since_str = since.isoformat()
        
        pipeline = [
            {"$match": {"date": {"$gte": since_str}, "extractedTopics": {"$exists": True, "$ne": []}}},
            {"$unwind": "$extractedTopics"},
            {"$group": {"_id": "$extractedTopics", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": limit}
        ]
        
        return await self.db.tg_posts.aggregate(pipeline).to_list(limit)


class TopicMomentumEngine:
    """Calculate topic momentum and detect spikes"""
    
    def __init__(self, repo: TopicRepository):
        self.repo = repo
    
    async def calculate(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Calculate momentum for top topics"""
        
        # Get top topics from 6h window
        top_topics = await self.repo.aggregate_topics(6, limit=limit)
        
        results = []
        
        for item in top_topics:
            topic = item["_id"]
            
            # Get counts for different windows
            m1 = await self.repo.count_mentions(topic, 1)
            m6 = await self.repo.count_mentions(topic, 6)
            m24 = await self.repo.count_mentions(topic, 24)
            
            # Calculate baseline (average per hour over 24h)
            baseline = m24 / 24 if m24 > 0 else 0.1
            
            # Momentum = how much above baseline
            momentum = round(m1 / baseline, 2) if baseline > 0 else 0
            
            # Spike detection
            is_spiking = momentum > 2.5 and m1 >= 3
            
            results.append({
                "topic": topic,
                "mentions_1h": m1,
                "mentions_6h": m6,
                "mentions_24h": m24,
                "baseline_24h": round(baseline, 2),
                "momentum": momentum,
                "isSpiking": is_spiking
            })
        
        # Sort by momentum
        results.sort(key=lambda x: x["momentum"], reverse=True)
        
        return results


async def ensure_topic_indexes(db):
    """Create indexes for topic queries"""
    try:
        await db.tg_posts.create_index([("extractedTopics", 1)])
        await db.tg_posts.create_index([("date", -1), ("extractedTopics", 1)])
        logger.info("Topic indexes created")
    except Exception as e:
        logger.warning(f"Topic index warning: {e}")
