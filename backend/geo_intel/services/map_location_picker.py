"""
Map Location Picker Service - Create events without sharing location

Two modes for creating events:
1. 📍 Використати мою локацію - Quick, uses user's current location
2. 🗺 Вказати на карті - Open map picker, user selects point

Features:
- WebApp integration for map picker
- Temporary location tokens
- Location validation
"""
import logging
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Location picker token expiry
TOKEN_EXPIRY_MINUTES = 30


class MapLocationPickerService:
    """Handles location selection for event creation"""
    
    def __init__(self, db):
        self.db = db
        self.tokens_collection = db.geo_location_tokens
        self.base_url = os.environ.get("REACT_APP_BACKEND_URL", "https://telegram-stack.preview.emergentagent.com")
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.tokens_collection.create_index("token", unique=True)
        await self.tokens_collection.create_index("actorId")
        await self.tokens_collection.create_index("expiresAt", expireAfterSeconds=0)
    
    async def create_picker_token(
        self,
        actor_id: str,
        signal_type: str = None,
        chat_id: int = None
    ) -> Dict[str, Any]:
        """
        Create a temporary token for map picker.
        User will open WebApp with this token.
        """
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
        
        doc = {
            "token": token,
            "actorId": actor_id,
            "chatId": chat_id,
            "signalType": signal_type,
            "status": "pending",
            "location": None,
            "createdAt": now,
            "expiresAt": expires_at,
        }
        
        await self.tokens_collection.insert_one(doc)
        
        # Generate WebApp URL
        webapp_url = f"{self.base_url}/map-picker?token={token}"
        
        return {
            "ok": True,
            "token": token,
            "webappUrl": webapp_url,
            "expiresAt": expires_at.isoformat()
        }
    
    async def set_location(
        self,
        token: str,
        lat: float,
        lng: float,
        address: str = None
    ) -> Dict[str, Any]:
        """
        Set location for a picker token.
        Called from WebApp after user selects location on map.
        """
        doc = await self.tokens_collection.find_one({"token": token})
        
        if not doc:
            return {"ok": False, "error": "Token not found"}
        
        if doc.get("status") != "pending":
            return {"ok": False, "error": "Token already used"}
        
        now = datetime.now(timezone.utc)
        
        # Validate coordinates
        if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
            return {"ok": False, "error": "Invalid coordinates"}
        
        await self.tokens_collection.update_one(
            {"token": token},
            {
                "$set": {
                    "status": "completed",
                    "location": {
                        "lat": lat,
                        "lng": lng,
                        "address": address
                    },
                    "completedAt": now
                }
            }
        )
        
        return {
            "ok": True,
            "token": token,
            "location": {"lat": lat, "lng": lng, "address": address}
        }
    
    async def get_token_location(self, token: str) -> Dict[str, Any]:
        """
        Get location from a completed token.
        Called by bot to create event with selected location.
        """
        doc = await self.tokens_collection.find_one({"token": token})
        
        if not doc:
            return {"ok": False, "error": "Token not found"}
        
        if doc.get("status") != "completed":
            return {"ok": False, "error": "Location not yet selected", "status": doc.get("status")}
        
        location = doc.get("location")
        
        return {
            "ok": True,
            "actorId": doc.get("actorId"),
            "signalType": doc.get("signalType"),
            "location": location,
            "chatId": doc.get("chatId")
        }
    
    async def invalidate_token(self, token: str):
        """Mark token as used/invalid"""
        await self.tokens_collection.update_one(
            {"token": token},
            {"$set": {"status": "used"}}
        )
    
    def get_location_mode_keyboard(self) -> Dict[str, Any]:
        """
        Keyboard for choosing location input mode.
        📍 Використати мою локацію - Quick, 1 tap
        🗺 Вказати на карті - Open map picker
        """
        return {
            "inline_keyboard": [
                [{"text": "📍 Використати мою локацію", "callback_data": "location_mode:current"}],
                [{"text": "🗺 Вказати на карті", "callback_data": "location_mode:map"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
    
    def get_map_picker_button(self, webapp_url: str) -> Dict[str, Any]:
        """
        Inline keyboard with WebApp button for map picker.
        Opens Telegram WebApp.
        """
        return {
            "inline_keyboard": [
                [{"text": "🗺 Відкрити карту", "web_app": {"url": webapp_url}}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
    
    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens (called by scheduler)"""
        now = datetime.now(timezone.utc)
        result = await self.tokens_collection.delete_many({
            "expiresAt": {"$lt": now}
        })
        return result.deleted_count
