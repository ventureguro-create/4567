"""
Bot User Service - Manage bot users (actors)
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BotUserService:
    """Service for managing geo bot users"""
    
    STATES = ["NEW", "ONBOARDED", "ACTIVE", "PAUSED"]
    
    def __init__(self, db):
        self.db = db
        self.collection = db.geo_bot_users
    
    async def get_or_create_user(
        self,
        telegram_chat_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing user or create new one"""
        actor_id = f"tg_{telegram_chat_id}"
        
        existing = await self.collection.find_one({"actorId": actor_id})
        
        if existing:
            # Update username if changed
            if username and existing.get("username") != username:
                await self.collection.update_one(
                    {"actorId": actor_id},
                    {"$set": {"username": username, "updatedAt": datetime.now(timezone.utc)}}
                )
            return {**existing, "_id": None, "isNew": False}
        
        # Create new user
        now = datetime.now(timezone.utc)
        doc = {
            "actorId": actor_id,
            "telegramChatId": telegram_chat_id,
            "username": username,
            "firstName": first_name,
            "state": "NEW",
            "createdAt": now,
            "updatedAt": now
        }
        
        await self.collection.insert_one(doc)
        logger.info(f"Created new bot user: {actor_id}")
        
        return {**doc, "_id": None, "isNew": True}
    
    async def get_user(self, actor_id: str) -> Optional[Dict[str, Any]]:
        """Get user by actor_id"""
        doc = await self.collection.find_one({"actorId": actor_id}, {"_id": 0})
        return doc
    
    async def get_user_by_chat_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get user by Telegram chat ID"""
        doc = await self.collection.find_one({"telegramChatId": chat_id}, {"_id": 0})
        return doc
    
    async def update_state(self, actor_id: str, state: str) -> bool:
        """Update user state"""
        if state not in self.STATES:
            return False
        
        result = await self.collection.update_one(
            {"actorId": actor_id},
            {"$set": {"state": state, "updatedAt": datetime.now(timezone.utc)}}
        )
        return result.modified_count > 0
    
    async def get_active_users(self) -> list:
        """Get all users with ACTIVE state and radar enabled"""
        cursor = self.collection.find(
            {"state": {"$in": ["ACTIVE", "ONBOARDED"]}},
            {"_id": 0}
        )
        return [doc async for doc in cursor]
    
    async def get_users_count(self) -> Dict[str, int]:
        """Get user counts by state"""
        pipeline = [
            {"$group": {"_id": "$state", "count": {"$sum": 1}}}
        ]
        
        result = {"total": 0, "by_state": {}}
        async for doc in self.collection.aggregate(pipeline):
            result["by_state"][doc["_id"]] = doc["count"]
            result["total"] += doc["count"]
        
        return result
