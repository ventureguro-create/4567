"""
Broadcast Service - Mass messaging to bot users
"""
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
BATCH_SIZE = 25  # Messages per batch
BATCH_DELAY = 1.0  # Seconds between batches (Telegram rate limit)


class BroadcastService:
    """Service for broadcasting messages to bot users"""
    
    def __init__(self, db):
        self.db = db
    
    async def send_message(self, chat_id: int, text: str, parse_mode: str = "Markdown", reply_markup: dict = None) -> Dict[str, Any]:
        """Send message to single user"""
        if not BOT_TOKEN:
            return {"ok": False, "error": "BOT_TOKEN not set"}
        
        try:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json=payload,
                    timeout=10.0
                )
                return response.json()
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def get_all_users(self, filter_active: bool = True) -> List[Dict[str, Any]]:
        """Get all bot users"""
        query = {}
        if filter_active:
            # Only users who have been active
            query["lastActivityAt"] = {"$exists": True}
        
        users = await self.db.geo_bot_users.find(
            query,
            {"_id": 0, "telegramChatId": 1, "username": 1, "firstName": 1}
        ).to_list(10000)
        
        return users
    
    async def get_subscribed_users(self) -> List[Dict[str, Any]]:
        """Get users with active subscription"""
        now = datetime.now(timezone.utc)
        
        # Get active subscriptions
        subscriptions = await self.db.subscriptions.find(
            {"status": "active", "expiresAt": {"$gt": now}},
            {"_id": 0, "userId": 1}
        ).to_list(10000)
        
        user_ids = [s["userId"] for s in subscriptions]
        
        # Get user details
        users = await self.db.geo_bot_users.find(
            {"actorId": {"$in": user_ids}},
            {"_id": 0, "telegramChatId": 1, "username": 1}
        ).to_list(10000)
        
        return users
    
    async def get_radar_users(self) -> List[Dict[str, Any]]:
        """Get users with radar enabled"""
        settings = await self.db.geo_bot_settings.find(
            {"radarEnabled": True},
            {"_id": 0, "actorId": 1}
        ).to_list(10000)
        
        user_ids = [s["actorId"] for s in settings]
        
        users = await self.db.geo_bot_users.find(
            {"actorId": {"$in": user_ids}},
            {"_id": 0, "telegramChatId": 1, "username": 1}
        ).to_list(10000)
        
        return users
    
    async def broadcast(
        self,
        text: str,
        target: str = "all",  # "all", "subscribed", "radar"
        parse_mode: str = "Markdown",
        reply_markup: dict = None,
        test_mode: bool = False
    ) -> Dict[str, Any]:
        """
        Broadcast message to users
        
        Args:
            text: Message text
            target: "all" | "subscribed" | "radar"
            parse_mode: Telegram parse mode
            reply_markup: Optional inline keyboard
            test_mode: If True, only count users without sending
        """
        # Get target users
        if target == "subscribed":
            users = await self.get_subscribed_users()
        elif target == "radar":
            users = await self.get_radar_users()
        else:
            users = await self.get_all_users()
        
        total_users = len(users)
        
        if test_mode:
            return {
                "ok": True,
                "testMode": True,
                "targetUsers": total_users,
                "target": target
            }
        
        if total_users == 0:
            return {"ok": True, "sent": 0, "failed": 0, "message": "No users to send"}
        
        # Create broadcast record
        broadcast_id = f"broadcast_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        broadcast_record = {
            "broadcastId": broadcast_id,
            "text": text[:200] + "..." if len(text) > 200 else text,
            "target": target,
            "totalUsers": total_users,
            "sent": 0,
            "failed": 0,
            "status": "running",
            "startedAt": datetime.now(timezone.utc),
            "completedAt": None
        }
        await self.db.broadcasts.insert_one(broadcast_record)
        
        # Send messages in batches
        sent = 0
        failed = 0
        failed_users = []
        
        for i in range(0, total_users, BATCH_SIZE):
            batch = users[i:i + BATCH_SIZE]
            
            for user in batch:
                chat_id = user.get("telegramChatId")
                if not chat_id:
                    continue
                
                result = await self.send_message(chat_id, text, parse_mode, reply_markup)
                
                if result.get("ok"):
                    sent += 1
                else:
                    failed += 1
                    failed_users.append({
                        "chatId": chat_id,
                        "error": result.get("description", result.get("error", "Unknown"))
                    })
            
            # Update progress
            await self.db.broadcasts.update_one(
                {"broadcastId": broadcast_id},
                {"$set": {"sent": sent, "failed": failed}}
            )
            
            # Rate limit delay
            if i + BATCH_SIZE < total_users:
                await asyncio.sleep(BATCH_DELAY)
        
        # Complete broadcast
        await self.db.broadcasts.update_one(
            {"broadcastId": broadcast_id},
            {
                "$set": {
                    "status": "completed",
                    "sent": sent,
                    "failed": failed,
                    "completedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Broadcast {broadcast_id} completed: {sent} sent, {failed} failed")
        
        return {
            "ok": True,
            "broadcastId": broadcast_id,
            "sent": sent,
            "failed": failed,
            "totalUsers": total_users,
            "failedUsers": failed_users[:10]  # Return first 10 failures
        }
    
    async def get_broadcast_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get broadcast history"""
        broadcasts = await self.db.broadcasts.find(
            {},
            {"_id": 0}
        ).sort("startedAt", -1).limit(limit).to_list(limit)
        
        return broadcasts
    
    async def get_broadcast_status(self, broadcast_id: str) -> Optional[Dict[str, Any]]:
        """Get broadcast status"""
        broadcast = await self.db.broadcasts.find_one(
            {"broadcastId": broadcast_id},
            {"_id": 0}
        )
        return broadcast


async def ensure_broadcast_indexes(db):
    """Create indexes for broadcast collection"""
    await db.broadcasts.create_index("broadcastId", unique=True)
    await db.broadcasts.create_index([("startedAt", -1)])
    logger.info("Broadcast indexes created")
