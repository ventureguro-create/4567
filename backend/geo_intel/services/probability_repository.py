"""
Probability Repository
Database operations for probability calculations
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict


class ProbabilityRepository:
    def __init__(self, db):
        self.db = db
    
    async def get_recent_events(self, days: int = 30) -> List[Dict]:
        """Get events from last N days"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        cursor = self.db.tg_geo_events.find(
            {"createdAt": {"$gte": since}},
            {"_id": 0}
        )
        return await cursor.to_list(10000)
    
    async def upsert_probability(self, doc: Dict):
        """Insert or update probability record"""
        await self.db.tg_geo_probabilities.update_one(
            {
                "placeKey": doc["placeKey"],
                "eventType": doc["eventType"]
            },
            {"$set": doc},
            upsert=True
        )
    
    async def get_top_probabilities(self, limit: int = 20) -> List[Dict]:
        """Get places with highest probability"""
        cursor = self.db.tg_geo_probabilities.find(
            {},
            {"_id": 0}
        ).sort("probabilityNow", -1).limit(limit)
        return await cursor.to_list(limit)
    
    async def get_probability_for_location(self, lat: float, lng: float, radius: float = 0.005) -> List[Dict]:
        """Get probabilities near a location"""
        cursor = self.db.tg_geo_probabilities.find({
            "lat": {"$gte": lat - radius, "$lte": lat + radius},
            "lng": {"$gte": lng - radius, "$lte": lng + radius}
        }, {"_id": 0})
        return await cursor.to_list(100)
