"""
Geo Radar Telegram Bot
Delivery channel for proximity alerts
Commands: /start, /radar_on, /radar_off, /test, /status
"""
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or os.environ.get("GEO_BOT_TOKEN")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", os.environ.get("APP_BASE_URL", "https://0b7a8e00-e255-4b11-9f97-a425aa046882.preview.emergentagent.com"))

# Telegram Stars subscription prices (in Stars)
SUBSCRIPTION_PRICES = {
    "pro_weekly": {"stars": 50, "days": 7, "label": "PRO 7 днів"},
    "pro_monthly": {"stars": 150, "days": 30, "label": "PRO 30 днів"},
}


class GeoRadarBot:
    """Telegram bot for Geo Radar alerts"""
    
    def __init__(self, db, token: str = None):
        self.db = db
        self.token = token or BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.running = False
        self.offset = 0
    
    async def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> dict:
        """Send message to chat"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json=payload,
                    timeout=10.0
                )
                return response.json()
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def get_updates(self, timeout: int = 30) -> list:
        """Get updates using long polling"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/getUpdates",
                    params={
                        "offset": self.offset,
                        "timeout": timeout,
                        "allowed_updates": ["message", "callback_query"]
                    },
                    timeout=timeout + 10
                )
                data = response.json()
                if data.get("ok"):
                    return data.get("result", [])
                return []
        except Exception as e:
            logger.error(f"Get updates error: {e}")
            return []
    
    async def handle_start(self, chat_id: int, user_id: int, username: str = None):
        """Handle /start command - register user"""
        actor_id = f"tg_{user_id}"
        
        # Save or update user
        await self.db.geo_bot_users.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "telegramChatId": chat_id,
                    "telegramUserId": user_id,
                    "username": username,
                    "radarEnabled": False,
                    "radius": 1000,
                    "lastLat": None,
                    "lastLng": None,
                    "updatedAt": datetime.now(timezone.utc)
                },
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        text = f"""
👋 <b>Вітаю в Geo Radar Bot!</b>

Я буду сповіщати вас про події поблизу:
🚓 Поліція • 🦠 Вірус • 🌧 Погода
🗑️ Сміття • ⚠️ Небезпека • 🔥 Інциденти

<b>Команди:</b>
/radar — відкрити Mini App
/subscribe — підписка PRO
/status — перевірити статус
/help — допомога
"""
        # Create inline keyboard with Mini App button
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "🗺️ Відкрити Radar",
                        "web_app": {"url": BASE_URL}
                    }
                ],
                [
                    {"text": "⭐ PRO підписка", "callback_data": "subscribe_pro"},
                    {"text": "👥 Реферали", "callback_data": "referrals"}
                ]
            ]
        }
        
        await self.send_message(chat_id, text.strip(), reply_markup=reply_markup)
        logger.info(f"User registered: {actor_id} (chat_id={chat_id})")
    
    async def handle_radar_on(self, chat_id: int, user_id: int):
        """Handle /radar_on command"""
        actor_id = f"tg_{user_id}"
        
        await self.db.geo_bot_users.update_one(
            {"actorId": actor_id},
            {"$set": {"radarEnabled": True, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        # Also create/update subscription
        await self.db.geo_alert_subscriptions.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "telegramChatId": chat_id,
                    "enabled": True,
                    "radius": 1000,
                    "eventTypes": ["virus", "trash"],
                    "updatedAt": datetime.now(timezone.utc)
                },
                "$setOnInsert": {
                    "createdAt": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        text = """
✅ <b>Радар увімкнено!</b>

Ви будете отримувати сповіщення про події поблизу.

⚠️ Щоб отримувати сповіщення, потрібно:
1. Відкрити карту в браузері
2. Дозволити геолокацію
3. Ваша позиція буде оновлюватися автоматично

🗺️ Відкрити карту та увімкнути геолокацію
"""
        await self.send_message(chat_id, text.strip())
        logger.info(f"Radar enabled for: {actor_id}")
    
    async def handle_radar_off(self, chat_id: int, user_id: int):
        """Handle /radar_off command"""
        actor_id = f"tg_{user_id}"
        
        await self.db.geo_bot_users.update_one(
            {"actorId": actor_id},
            {"$set": {"radarEnabled": False, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        await self.db.geo_alert_subscriptions.update_one(
            {"actorId": actor_id},
            {"$set": {"enabled": False, "updatedAt": datetime.now(timezone.utc)}}
        )
        
        text = """
🔇 <b>Радар вимкнено</b>

Ви більше не будете отримувати сповіщення.

Щоб увімкнути знову — /radar_on
"""
        await self.send_message(chat_id, text.strip())
        logger.info(f"Radar disabled for: {actor_id}")
    
    async def handle_status(self, chat_id: int, user_id: int):
        """Handle /status command"""
        actor_id = f"tg_{user_id}"
        
        user = await self.db.geo_bot_users.find_one({"actorId": actor_id})
        sub = await self.db.geo_alert_subscriptions.find_one({"actorId": actor_id})
        
        if not user:
            text = "❌ Ви ще не зареєстровані. Натисніть /start"
        else:
            radar_status = "✅ Увімкнено" if user.get("radarEnabled") else "🔇 Вимкнено"
            radius = sub.get("radius", 1000) if sub else 1000
            has_location = "✅ Так" if user.get("lastLat") else "❌ Ні"
            
            text = f"""
📊 <b>Статус Geo Radar</b>

🎯 Радар: {radar_status}
📍 Геолокація: {has_location}
📏 Радіус: {radius} м

Типи подій: 🦠 Вірус, 🗑️ Сміття
"""
        
        await self.send_message(chat_id, text.strip())
    
    async def handle_test(self, chat_id: int, user_id: int):
        """Handle /test command - send test alert"""
        text = """
🔔 <b>Тестове сповіщення</b>

⚠️ Увага — сигнал поблизу

🦠 <b>Крещатик 22</b>
Тип: вірус

📏 Відстань: <b>420 м</b>
🕐 Час: 5 хв тому
📊 Впевненість: 🟢 Висока

🗺️ <a href="{BASE_URL}">Відкрити карту</a>

<i>Це тестове повідомлення</i>
""".replace("{BASE_URL}", BASE_URL)
        
        await self.send_message(chat_id, text.strip())
        logger.info(f"Test alert sent to chat_id={chat_id}")
    
    async def handle_location(self, chat_id: int, user_id: int, lat: float, lng: float):
        """Handle location message - update user position"""
        actor_id = f"tg_{user_id}"
        
        await self.db.geo_bot_users.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "lastLat": lat,
                    "lastLng": lng,
                    "locationUpdatedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        await self.db.geo_alert_subscriptions.update_one(
            {"actorId": actor_id},
            {
                "$set": {
                    "lastLat": lat,
                    "lastLng": lng,
                    "updatedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        text = f"""
📍 <b>Позицію оновлено</b>

Координати: {lat:.5f}, {lng:.5f}

Тепер ви будете отримувати сповіщення про події поблизу цієї точки.
"""
        await self.send_message(chat_id, text.strip())
        logger.info(f"Location updated for {actor_id}: {lat}, {lng}")
    
    async def send_message_with_keyboard(
        self, 
        chat_id: int, 
        text: str, 
        reply_markup: dict = None,
        parse_mode: str = "Markdown"
    ) -> dict:
        """Send message with keyboard"""
        try:
            async with httpx.AsyncClient() as client:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
                if reply_markup:
                    payload["reply_markup"] = reply_markup  # No json.dumps - httpx handles it
                
                response = await client.post(
                    f"{self.api_url}/sendMessage",
                    json=payload,
                    timeout=10.0
                )
                result = response.json()
                if not result.get("ok"):
                    logger.error(f"Send message failed: {result}")
                return result
        except Exception as e:
            logger.error(f"Send message error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def process_update(self, update: dict):
        """Process single update using new BotCommandRouter"""
        from .bot_command_router import BotCommandRouter
        
        # Create send function that uses our bot
        async def send_func(chat_id, text, reply_markup=None, parse_mode=None):
            return await self.send_message_with_keyboard(
                chat_id, text, reply_markup, parse_mode or "Markdown"
            )
        
        router = BotCommandRouter(self.db, send_func)
        result = await router.handle_update(update)
        
        logger.debug(f"Update processed: {result}")
        return result
    
    async def run_polling(self):
        """Run bot with long polling"""
        if not self.token:
            logger.warning("TG_BOT_TOKEN not set, bot disabled")
            return
        
        logger.info("Geo Radar Bot started polling")
        self.running = True
        
        while self.running:
            try:
                updates = await self.get_updates()
                
                for update in updates:
                    self.offset = update.get("update_id", 0) + 1
                    logger.info(f"Processing update: {update.get('update_id')}")
                    try:
                        await self.process_update(update)
                    except Exception as e:
                        logger.error(f"Error processing update: {e}", exc_info=True)
                
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    def stop(self):
        """Stop polling"""
        self.running = False


# Global bot instance
_bot_instance: Optional[GeoRadarBot] = None


def get_bot(db) -> GeoRadarBot:
    """Get or create bot instance"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = GeoRadarBot(db)
    return _bot_instance


async def start_bot(db):
    """Initialize bot without polling (webhook mode)"""
    bot = get_bot(db)
    # Don't start polling - we use webhook
    logger.info("Geo Radar Bot initialized (webhook mode)")
    return bot
