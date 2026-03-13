"""
Engagement Anomaly Engine - Detect unusual post performance
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class AnomalyRepository:
    """Repository for channel statistics"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_channel_stats(self, username: str, days: int = 14) -> Optional[Dict]:
        """Get average and std for channel engagement metrics"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        since_str = since.isoformat()
        
        pipeline = [
            {"$match": {
                "username": username,
                "date": {"$gte": since_str}
            }},
            {"$group": {
                "_id": None,
                "avgViews": {"$avg": "$views"},
                "stdViews": {"$stdDevPop": "$views"},
                "avgForwards": {"$avg": "$forwards"},
                "stdForwards": {"$stdDevPop": "$forwards"},
                "avgReplies": {"$avg": "$replies"},
                "stdReplies": {"$stdDevPop": "$replies"},
                "postCount": {"$sum": 1}
            }}
        ]
        
        result = await self.db.tg_posts.aggregate(pipeline).to_list(1)
        return result[0] if result else None


class AnomalyEngine:
    """Detect engagement anomalies using z-score"""
    
    def __init__(self, repo: AnomalyRepository):
        self.repo = repo
        self._stats_cache = {}  # Simple in-memory cache
    
    def z_score(self, value: float, avg: float, std: float) -> float:
        """Calculate z-score"""
        if not std or std == 0:
            return 0
        return (value - avg) / std
    
    async def get_channel_stats_cached(self, username: str) -> Optional[Dict]:
        """Get stats with simple caching"""
        if username in self._stats_cache:
            cached = self._stats_cache[username]
            # Cache for 10 minutes
            if (datetime.now(timezone.utc) - cached["cachedAt"]).seconds < 600:
                return cached["stats"]
        
        stats = await self.repo.get_channel_stats(username)
        if stats:
            self._stats_cache[username] = {
                "stats": stats,
                "cachedAt": datetime.now(timezone.utc)
            }
        return stats
    
    async def evaluate_post(self, post: Dict) -> Optional[Dict[str, Any]]:
        """Evaluate if post is anomalous"""
        username = post.get("username")
        if not username:
            return None
        
        stats = await self.get_channel_stats_cached(username)
        if not stats or stats.get("postCount", 0) < 10:
            # Not enough data for baseline
            return None
        
        views = post.get("views", 0) or 0
        forwards = post.get("forwards", 0) or 0
        replies = post.get("replies", 0) or 0
        
        views_z = self.z_score(views, stats.get("avgViews", 0), stats.get("stdViews", 1))
        forwards_z = self.z_score(forwards, stats.get("avgForwards", 0), stats.get("stdForwards", 1))
        replies_z = self.z_score(replies, stats.get("avgReplies", 0), stats.get("stdReplies", 1))
        
        # Weighted anomaly score
        anomaly_score = max(views_z, forwards_z * 1.2, replies_z * 1.5)
        
        # Threshold for anomaly
        is_anomaly = anomaly_score > 2.5
        
        return {
            "username": username,
            "messageId": post.get("messageId"),
            "isAnomaly": is_anomaly,
            "anomalyScore": round(anomaly_score, 2),
            "viewsZ": round(views_z, 2),
            "forwardsZ": round(forwards_z, 2),
            "repliesZ": round(replies_z, 2)
        }
