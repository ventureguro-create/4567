"""
Bot Command Router - Main Telegram bot handler for Geo module
Full Telegram-first control layer
"""
import logging
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, Awaitable

from .bot_user_service import BotUserService
from .bot_settings_service import BotSettingsService, EVENT_TYPES
from .bot_location_service import BotLocationService
from .bot_keyboard_builder import BotKeyboardBuilder, EVENT_ICONS, EVENT_LABELS
from .bot_alert_service import BotAlertService
from .bot_status_service import BotStatusService
from .bot_summary_service import BotSummaryService

logger = logging.getLogger(__name__)


class BotCommandRouter:
    """
    Main command router for Geo Radar Bot
    Handles all commands, callbacks, and messages
    """
    
    def __init__(self, db, send_message_func: Callable[..., Awaitable[Any]]):
        """
        Args:
            db: MongoDB database instance
            send_message_func: Async function to send messages
                signature: (chat_id, text, reply_markup=None, parse_mode=None)
        """
        self.db = db
        self.send_message = send_message_func
        
        # Initialize services
        self.user_service = BotUserService(db)
        self.settings_service = BotSettingsService(db)
        self.location_service = BotLocationService(db)
        self.keyboard = BotKeyboardBuilder()
        self.alert_service = BotAlertService(db)
        self.status_service = BotStatusService(db)
        self.summary_service = BotSummaryService(db)
    
    # ==================== Main Router ====================
    
    async def handle_update(self, update: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point for all Telegram updates"""
        
        try:
            # Handle pre-checkout query (payment validation)
            if "pre_checkout_query" in update:
                return await self._handle_pre_checkout(update["pre_checkout_query"])
            
            # Handle successful payment
            if update.get("message", {}).get("successful_payment"):
                return await self._handle_successful_payment(update["message"])
            
            # Handle callback query (inline button press)
            if "callback_query" in update:
                return await self._handle_callback(update["callback_query"])
            
            # Handle message
            message = update.get("message", {})
            
            # Handle photo message (for report flow)
            if "photo" in message:
                logger.info(f"Photo message received. Caption: {message.get('caption', 'NO CAPTION')}")
                from .report_bot import USER_STATES
                actor_id = f"tg_{message['chat']['id']}"
                state = USER_STATES.get(actor_id, {})
                logger.info(f"User state for {actor_id}: {state}")
                return await self._handle_photo(message)
            
            # Handle location message
            if "location" in message:
                return await self._handle_location(message)
            
            # Handle text message
            text = message.get("text", "")
            
            # Check if it's a command
            if text.startswith("/"):
                return await self._handle_command(message)
            
            # Handle reply keyboard buttons
            return await self._handle_button(message)
            
        except Exception as e:
            logger.error(f"Error handling update: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}
    
    # ==================== Command Handlers ====================
    
    async def _handle_command(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /commands"""
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user_data = message.get("from", {})
        
        # Parse command and arguments
        parts = text.split()
        command = parts[0].lower().replace("@", "").split("@")[0]
        args = parts[1] if len(parts) > 1 else None
        
        # Handle /start with referral code
        if command == "/start" and args and args.startswith("ref_"):
            from .referral_bot import process_start_referral
            actor_id = f"tg_{chat_id}"
            await process_start_referral(
                self.db,
                user_id=actor_id,
                start_param=args,
                username=user_data.get("username")
            )
        
        handlers = {
            "/start": self.cmd_start,
            "/help": self.cmd_help,
            "/status": self.cmd_status,
            "/radar": self.cmd_radar,  # Open Mini App
            "/radar_on": self.cmd_radar_on,
            "/radar_off": self.cmd_radar_off,
            "/radius": self.cmd_radius,
            "/types": self.cmd_types,
            "/location": self.cmd_location,
            "/summary": self.cmd_summary,
            "/test": self.cmd_test,
            "/settings": self.cmd_settings,
            # Referral commands
            "/referrals": self.cmd_referrals,
            "/withdraw": self.cmd_withdraw,
            "/subscribe": self.cmd_subscribe,
            # Admin command
            "/admin": self.cmd_admin,
        }
        
        handler = handlers.get(command)
        if handler:
            return await handler(chat_id, user_data)
        
        return {"ok": True, "handled": False}
    
    async def cmd_start(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /start command - NEW Clean UX with Mini App button"""
        import os
        APP_URL = os.environ.get("APP_BASE_URL", "https://0b7a8e00-e255-4b11-9f97-a425aa046882.preview.emergentagent.com")
        
        # Create or get user
        user = await self.user_service.get_or_create_user(
            telegram_chat_id=chat_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name")
        )
        
        # Create default settings
        await self.settings_service.get_or_create_settings(user["actorId"])
        
        # Welcome message
        text = (
            "Вітаю в *RADAR* 📡\n\n"
            "Дивись події навколо в реальному часі:\n"
            "🚓 Поліція • 🦠 Вірус • 🌧 Погода\n"
            "🗑 Сміття • ⚠️ Небезпека • 🔥 Інциденти\n\n"
            "👇 Натисни кнопку, щоб відкрити карту"
        )
        
        # Inline keyboard with Mini App button
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "🗺️ Відкрити Radar",
                        "web_app": {"url": APP_URL}
                    }
                ],
                [
                    {"text": "⭐ PRO підписка", "callback_data": "subscribe_pay"},
                    {"text": "👥 Реферали", "callback_data": "menu_referrals"}
                ],
                [
                    {"text": "⚙️ Налаштування", "callback_data": "menu_settings"},
                    {"text": "❓ Допомога", "callback_data": "menu_help"}
                ]
            ]
        }
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "start", "isNew": user.get("isNew")}
    
    async def cmd_radar(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /radar command - Open Mini App"""
        import os
        APP_URL = os.environ.get("APP_BASE_URL", "https://0b7a8e00-e255-4b11-9f97-a425aa046882.preview.emergentagent.com")
        
        text = "🗺️ *Відкрити Radar*\n\nНатисни кнопку нижче:"
        
        reply_markup = {
            "inline_keyboard": [
                [
                    {
                        "text": "🗺️ Відкрити Radar",
                        "web_app": {"url": APP_URL}
                    }
                ]
            ]
        }
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "radar"}

    async def cmd_help(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /help command - Compact help with privacy section"""
        text = (
            "❓ *Допомога*\n\n"
            "Як працює Radar:\n\n"
            "1️⃣ Надішліть локацію\n"
            "2️⃣ Увімкніть радар\n"
            "3️⃣ Отримуйте або надсилайте сигнали\n\n"
            "Чим більше підтверджень — тим точніші сигнали.\n\n"
            "🔒 *Конфіденційність*\n\n"
            "Radar не зберігає історію переміщень.\n\n"
            "Локація використовується тільки для визначення сигналів поруч "
            "та автоматично видаляється після завершення таймера."
        )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.back_button("menu_settings"),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "help"}
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "help"}
    
    async def cmd_status(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /status command"""
        actor_id = f"tg_{chat_id}"
        
        user = await self.user_service.get_user(actor_id)
        settings = await self.settings_service.get_or_create_settings(actor_id)
        location = await self.location_service.get_location(actor_id)
        
        status_text = await self.status_service.build_status(user or {}, settings, location)
        
        await self.send_message(
            chat_id=chat_id,
            text=status_text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "status"}
    
    async def cmd_radar_on(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /radar_on command"""
        actor_id = f"tg_{chat_id}"
        
        # Check if location is set
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="📍 Надішліть локацію, щоб увімкнути радар",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        await self.settings_service.set_radar_enabled(actor_id, True)
        await self.user_service.update_state(actor_id, "ACTIVE")
        
        settings = await self.settings_service.get_settings(actor_id)
        radius = settings.get("radius", 1000) if settings else 1000
        
        # Show radar screen with enabled state
        await self.send_message(
            chat_id=chat_id,
            text=f"📡 *Радар активний*\n\n📍 Радіус: {radius} м",
            reply_markup=self.keyboard.radar_menu(is_enabled=True, radius=radius),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "radar_on"}
    
    async def cmd_radar_off(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /radar_off command"""
        actor_id = f"tg_{chat_id}"
        
        await self.settings_service.set_radar_enabled(actor_id, False)
        await self.user_service.update_state(actor_id, "PAUSED")
        
        # Show radar screen with disabled state - user can turn back on
        await self.send_message(
            chat_id=chat_id,
            text="📡 *Радар вимкнено*",
            reply_markup=self.keyboard.radar_menu(is_enabled=False),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "radar_off"}
    
    async def cmd_radius(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /radius command"""
        actor_id = f"tg_{chat_id}"
        settings = await self.settings_service.get_or_create_settings(actor_id)
        
        await self.send_message(
            chat_id=chat_id,
            text="🎯 Виберіть радіус:",
            reply_markup=self.keyboard.radius_options(settings.get("radius", 1000))
        )
        
        return {"ok": True, "action": "radius"}
    
    async def cmd_types(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /types command"""
        actor_id = f"tg_{chat_id}"
        settings = await self.settings_service.get_or_create_settings(actor_id)
        
        await self.send_message(
            chat_id=chat_id,
            text="🧩 Виберіть типи сигналів:",
            reply_markup=self.keyboard.event_types(settings.get("eventTypes", []))
        )
        
        return {"ok": True, "action": "types"}
    
    async def cmd_location(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /location command"""
        await self.send_message(
            chat_id=chat_id,
            text="📍 Надішліть свою геолокацію:",
            reply_markup=self.keyboard.location_request()
        )
        
        return {"ok": True, "action": "location"}
    
    async def cmd_summary(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /summary command"""
        actor_id = f"tg_{chat_id}"
        location = await self.location_service.get_location(actor_id)
        settings = await self.settings_service.get_settings(actor_id)
        
        if location:
            text = await self.summary_service.generate_user_summary(
                actor_id=actor_id,
                lat=location["lat"],
                lng=location["lng"],
                radius=settings.get("radius", 1000) if settings else 1000
            )
        else:
            text = await self.summary_service.generate_summary(hours=24)
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "summary"}
    
    async def cmd_test(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /test command"""
        await self.send_message(
            chat_id=chat_id,
            text="✅ *Тестове повідомлення*\n\nGeo Radar Bot працює коректно.",
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "test"}
    
    async def cmd_settings(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /settings command"""
        await self.send_message(
            chat_id=chat_id,
            text="⚙️ *Налаштування*",
            reply_markup=self.keyboard.settings_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "settings"}
    
    # ==================== Referral Commands ====================
    
    async def cmd_referrals(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /referrals command"""
        from .referral_bot import handle_referrals_command
        actor_id = f"tg_{chat_id}"
        return await handle_referrals_command(self.db, chat_id, actor_id)
    
    async def cmd_withdraw(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /withdraw command"""
        from .referral_bot import handle_withdraw_command
        actor_id = f"tg_{chat_id}"
        return await handle_withdraw_command(self.db, chat_id, actor_id)
    
    async def cmd_subscribe(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /subscribe command"""
        from .referral_bot import handle_subscribe_command
        actor_id = f"tg_{chat_id}"
        return await handle_subscribe_command(self.db, chat_id, actor_id)
    
    async def cmd_admin(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle /admin command - show admin panel for admins only"""
        telegram_id = user_data.get("id", 0)
        return await self.show_admin_panel(chat_id, telegram_id)
    
    # ==================== Payment Handlers ====================
    
    async def _handle_pre_checkout(self, pre_checkout_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle pre_checkout_query - validate payment before processing"""
        query_id = pre_checkout_query.get("id")
        user_data = pre_checkout_query.get("from", {})
        user_id = f"tg_{user_data.get('id')}"
        payload = pre_checkout_query.get("invoice_payload", "")
        
        from .telegram_stars_payment import PaymentService
        payment_svc = PaymentService(self.db)
        result = await payment_svc.handle_pre_checkout(query_id, user_id, payload)
        
        logger.info(f"Pre-checkout handled: {query_id} - {result.get('ok')}")
        return {"ok": True, "action": "pre_checkout", "result": result}
    
    async def _handle_successful_payment(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle successful_payment - process payment and activate subscription"""
        chat_id = message["chat"]["id"]
        user_data = message.get("from", {})
        user_id = f"tg_{chat_id}"
        payment_data = message.get("successful_payment", {})
        
        from .telegram_stars_payment import PaymentService
        payment_svc = PaymentService(self.db)
        result = await payment_svc.handle_successful_payment(user_id, chat_id, payment_data)
        
        if result.get("ok"):
            # Send confirmation
            await self.send_message(
                chat_id=chat_id,
                text="✅ *Дякуємо за оплату!*\n\nВаша підписка активована.\n\n💡 Запрошуйте друзів і заробляйте $0.30 за кожного!",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            
            logger.info(f"Payment processed: {user_id} - {payment_data.get('total_amount')} Stars")
        else:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Помилка обробки платежу. Зверніться до підтримки.",
                reply_markup=self.keyboard.main_menu()
            )
        
        return {"ok": True, "action": "successful_payment", "result": result}
    
    async def cmd_report_signal(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle report signal button - start reporting flow"""
        actor_id = f"tg_{chat_id}"
        
        # Check if user has location
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Спочатку надішліть свою локацію",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        # Check spam limit
        from .crowd_signal_service import CrowdSignalService
        crowd_service = CrowdSignalService(self.db)
        spam_check = await crowd_service.can_user_report(actor_id)
        
        if not spam_check["allowed"]:
            await self.send_message(
                chat_id=chat_id,
                text=f"⚠️ {spam_check['reason']}\n\nСпробуйте пізніше.",
                reply_markup=self.keyboard.main_menu()
            )
            return {"ok": False, "error": "spam_limit"}
        
        # Show event type selection
        await self.send_message(
            chat_id=chat_id,
            text="➕ *Повідомити сигнал*\n\nЩо сталося?",
            reply_markup=self.keyboard.report_event_types(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "report_start"}
    
    async def cmd_report_new(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 🚨 Повідомити - New fast report flow (Waze-style)"""
        from .report_bot import handle_report_command
        
        actor_id = f"tg_{chat_id}"
        username = user_data.get("username")
        
        return await handle_report_command(self.db, chat_id, actor_id, username)
    
    async def cmd_leaderboard(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle 🏆 Рейтинг - Show leaderboard"""
        from .report_bot import handle_leaderboard_command
        
        return await handle_leaderboard_command(self.db, chat_id)
    
    async def cmd_nearby(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle nearby button - show what's around"""
        actor_id = f"tg_{chat_id}"
        
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Спочатку надішліть свою локацію",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        settings = await self.settings_service.get_settings(actor_id)
        radius = settings.get("radius", 1000) if settings else 1000
        
        # Get nearby events
        from .proximity import get_nearby_events
        result = await get_nearby_events(
            self.db,
            lat=location["lat"],
            lng=location["lng"],
            radius_m=radius,
            days=1
        )
        
        events = result.get("items", [])
        
        if not events:
            text = f"✅ *Поруч чисто*\n\nУ радіусі {radius} м немає активних сигналів."
        else:
            # Group by type
            by_type = {}
            for e in events:
                etype = e.get("eventType", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
            
            lines = [
                f"🔎 *Що поруч* (радіус {radius} м)",
                "",
                f"Знайдено {len(events)} сигналів:",
                ""
            ]
            
            for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
                icon = EVENT_ICONS.get(etype, "•")
                lines.append(f"{icon} {etype}: {cnt}")
            
            # Nearest
            if events:
                nearest = events[0]
                dist = nearest.get("distance", "?")
                lines.append("")
                lines.append(f"Найближчий: {dist} м")
            
            text = "\n".join(lines)
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "nearby", "count": len(events)}
    
    async def cmd_district(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle district statistics button"""
        actor_id = f"tg_{chat_id}"
        
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Спочатку надішліть свою локацію",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        settings = await self.settings_service.get_settings(actor_id)
        radius = settings.get("radius", 2000) if settings else 2000
        
        # Get events for last 24 hours
        from datetime import datetime, timezone, timedelta
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        cursor = self.db.tg_geo_events.find({
            "createdAt": {"$gte": since},
            "location": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [location["lng"], location["lat"]]},
                    "$maxDistance": radius * 2
                }
            }
        }).limit(100)
        
        events = [e async for e in cursor]
        
        if not events:
            text = f"📊 *Статистика району*\n\nЗа останні 24 години сигналів не зафіксовано."
        else:
            # Count by type
            by_type = {}
            hours_dist = {}
            for e in events:
                etype = e.get("eventType", "unknown")
                by_type[etype] = by_type.get(etype, 0) + 1
                
                created = e.get("createdAt")
                if created:
                    hour = created.hour
                    hours_dist[hour] = hours_dist.get(hour, 0) + 1
            
            # Find peak hour
            peak_hour = max(hours_dist.items(), key=lambda x: x[1]) if hours_dist else (12, 0)
            
            # Calculate risk level
            total = len(events)
            if total >= 10:
                risk = "🔴 Висока"
            elif total >= 5:
                risk = "🟡 Помірна"
            else:
                risk = "🟢 Низька"
            
            lines = [
                "📊 *Статистика району*",
                f"_(радіус {radius*2} м, 24 год)_",
                "",
                f"Всього сигналів: {total}",
                f"Активність: {risk}",
                "",
                "*За типом:*"
            ]
            
            for etype, cnt in sorted(by_type.items(), key=lambda x: -x[1]):
                icon = EVENT_ICONS.get(etype, "•")
                lines.append(f"{icon} {etype}: {cnt}")
            
            lines.append("")
            lines.append(f"⏰ Пік активності: {peak_hour[0]}:00-{(peak_hour[0]+1)%24}:00")
            
            text = "\n".join(lines)
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "district"}
    
    async def cmd_forecast(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle forecast button - predict next events"""
        actor_id = f"tg_{chat_id}"
        
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Спочатку надішліть свою локацію",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        settings = await self.settings_service.get_settings(actor_id)
        radius = settings.get("radius", 1000) if settings else 1000
        
        # Get probability predictions
        from .predictor import get_place_prediction
        
        try:
            result = await get_place_prediction(
                self.db,
                lat=location["lat"],
                lng=location["lng"],
                radius_m=radius
            )
            
            probability = result.get("probability", 0)
            top_places = result.get("topPlaces", [])[:3]
            
            # Risk level based on probability
            if probability >= 0.7:
                risk = "🔴 Висока"
            elif probability >= 0.4:
                risk = "🟡 Помірна"
            else:
                risk = "🟢 Низька"
            
            lines = [
                "🔮 *Прогноз*",
                "",
                f"Ймовірність сигналу в радіусі {radius} м",
                f"у наступні 2 години:",
                "",
                f"*{int(probability * 100)}%*",
                "",
                f"Рівень ризику: {risk}",
            ]
            
            if top_places:
                lines.append("")
                lines.append("*Найбільш ймовірні точки:*")
                for i, place in enumerate(top_places, 1):
                    lines.append(f"{i}. {place.get('title', 'Невідомо')}")
            
            text = "\n".join(lines)
            
        except Exception as e:
            text = "🔮 *Прогноз*\n\nНедостатньо даних для прогнозу.\nСпробуйте пізніше."
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "forecast"}
    
    async def cmd_history(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle history button - show recent signals"""
        actor_id = f"tg_{chat_id}"
        
        location = await self.location_service.get_location(actor_id)
        if not location:
            await self.send_message(
                chat_id=chat_id,
                text="❌ Спочатку надішліть свою локацію",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location"}
        
        settings = await self.settings_service.get_settings(actor_id)
        radius = settings.get("radius", 2000) if settings else 2000
        
        # Get recent events
        from datetime import datetime, timezone, timedelta
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        
        cursor = self.db.tg_geo_events.find({
            "createdAt": {"$gte": since},
            "location": {
                "$nearSphere": {
                    "$geometry": {"type": "Point", "coordinates": [location["lng"], location["lat"]]},
                    "$maxDistance": radius
                }
            }
        }).sort("createdAt", -1).limit(10)
        
        events = [e async for e in cursor]
        
        if not events:
            text = "📜 *Історія*\n\nЗа останні 24 години сигналів не було."
        else:
            lines = ["📜 *Історія сигналів*", ""]
            
            now = datetime.now(timezone.utc)
            for e in events:
                icon = EVENT_ICONS.get(e.get("eventType", ""), "•")
                title = e.get("title", "Невідомо")
                
                created = e.get("createdAt")
                if created:
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age_min = int((now - created).total_seconds() / 60)
                    
                    if age_min < 60:
                        age_str = f"{age_min} хв"
                    else:
                        age_str = f"{age_min // 60} год"
                else:
                    age_str = "?"
                
                # Source indicator
                source = e.get("source", "")
                if source == "user":
                    src_icon = "👤"
                else:
                    src_icon = "📡"
                
                lines.append(f"{icon} {title} — {age_str} {src_icon}")
            
            text = "\n".join(lines)
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "history"}
    
    async def cmd_activity(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle activity button - show hot zones"""
        actor_id = f"tg_{chat_id}"
        
        # Get active risk zones
        from .risk_zone_repository import RiskZoneRepository
        repo = RiskZoneRepository(self.db)
        zones = await repo.get_active_zones()
        
        if not zones:
            text = "🔥 *Активність*\n\n✅ Наразі гарячих зон не виявлено."
        else:
            # Sort by risk score
            zones.sort(key=lambda x: -x.get("riskScore", 0))
            
            lines = ["🔥 *Найбільш активні зони*", ""]
            
            for i, zone in enumerate(zones[:5], 1):
                etype = zone.get("eventType", "")
                icon = EVENT_ICONS.get(etype, "•")
                risk = zone.get("riskScore", 0)
                count = zone.get("eventCount", 0)
                
                # Risk level indicator
                if risk >= 0.7:
                    level = "🔴"
                elif risk >= 0.4:
                    level = "🟡"
                else:
                    level = "🟢"
                
                lines.append(f"{i}. {icon} {etype} — {count} сигналів {level}")
            
            # Add location context if user has location
            location = await self.location_service.get_location(actor_id)
            if location:
                near_zones = await repo.get_zones_near_location(
                    location["lat"], location["lng"], radius_m=2000
                )
                if near_zones:
                    lines.append("")
                    lines.append(f"⚠️ {len(near_zones)} зон поруч з вами!")
            
            text = "\n".join(lines)
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "activity"}
    
    # ==================== Location Handler ====================
    
    async def _handle_location(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle location message"""
        from .report_bot import handle_location_message, USER_STATES
        
        chat_id = message["chat"]["id"]
        location = message.get("location")
        actor_id = f"tg_{chat_id}"
        user_data = message.get("from", {})
        
        # Check if location is valid
        if not location or not location.get("latitude") or not location.get("longitude"):
            # Location blocked or not sent properly
            text = (
                "⚠️ *Геолокацію не отримано*\n\n"
                "Перевірте налаштування:\n"
                "1. Дозвольте доступ до геолокації в налаштуваннях телефону\n"
                "2. Увімкніть GPS\n"
                "3. Дайте дозвіл Telegram на геолокацію\n\n"
                "Спробуйте ще раз 👇"
            )
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=self.keyboard.location_request(),
                parse_mode="Markdown"
            )
            return {"ok": False, "error": "location_blocked"}
        
        lat = location["latitude"]
        lng = location["longitude"]
        is_live = "live_period" in location
        
        # Check if user is in report flow
        state = USER_STATES.get(actor_id)
        
        # Handle new instant send flow
        if state and state.get("step") == "waiting_location_instant":
            event_type = state.get("signalType")
            # Save location first
            await self.location_service.update_location(actor_id, lat, lng, is_live)
            # Now create signal
            return await self._handle_instant_send(chat_id, actor_id, event_type)
        
        # Handle new detailed send flow
        if state and state.get("step") == "waiting_location_detailed":
            event_type = state.get("signalType")
            description = state.get("description")
            photo_url = state.get("photoUrl")
            event_emoji = state.get("event_emoji", "📍")
            # Save location first
            await self.location_service.update_location(actor_id, lat, lng, is_live)
            # Clear state
            USER_STATES.pop(actor_id, None)
            # Now create signal
            return await self._create_detailed_signal(chat_id, actor_id, event_type, description, photo_url)
        
        # Legacy flow
        if state and state.get("step") == "send_location":
            # Handle as report location
            return await handle_location_message(
                self.db, chat_id, actor_id, lat, lng,
                user_data.get("username")
            )
        
        # Normal location save
        await self.location_service.update_location(actor_id, lat, lng, is_live)
        
        # Create Geo Session with TTL
        settings = await self.settings_service.get_or_create_settings(actor_id)
        location_mode = settings.get("locationMode", "15m")
        radius = settings.get("radius", 1000)
        
        from .geo_session_service import GeoSessionService
        session_svc = GeoSessionService(self.db)
        session = await session_svc.create_session(
            user_id=actor_id,
            lat=lat,
            lng=lng,
            radius=radius,
            mode=location_mode
        )
        
        # Enable radar
        await self.settings_service.set_radar_enabled(actor_id, True)
        
        # Update user state
        await self.user_service.update_state(actor_id, "ACTIVE")
        
        # Build response with session info and privacy note
        if location_mode == "none":
            text = "📍 Локацію отримано (не зберігається)"
        else:
            mode_labels = {
                "5m": "5 хв",
                "15m": "15 хв",
                "1h": "1 година",
                "1d": "24 години",
                "permanent": "24 години (авто-оновлення)"
            }
            ttl_label = mode_labels.get(location_mode, location_mode)
            
            text = (
                f"📍 *Локацію збережено*\n\n"
                f"⏱ Час дії: {ttl_label}\n"
                f"📡 Радіус: {radius} м\n\n"
                f"🔒 Після завершення таймера локація автоматично видаляється."
            )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "location_saved", "lat": lat, "lng": lng, "mode": location_mode}
    
    async def _handle_photo(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle photo message (for report flow)
        
        Supports multiple states:
        - waiting_photo: legacy flow waiting for photo only
        - waiting_content: new flow waiting for photo and/or text (caption)
        
        Photo with caption is handled as single message - caption is the description.
        """
        from .report_bot import handle_photo_message, USER_STATES
        from .report_ingestion import create_user_report, update_radar_score
        import os
        
        chat_id = message["chat"]["id"]
        actor_id = f"tg_{chat_id}"
        user_data = message.get("from", {})
        
        # Get caption from photo message (text sent with photo)
        caption = message.get("caption", "")
        
        # Check if user is in report flow
        state = USER_STATES.get(actor_id)
        
        # Handle waiting_photo_optional - user chose to add photo after skipping description
        if state and state.get("step") == "waiting_photo_optional":
            event_type = state.get("signalType")
            event_emoji = state.get("event_emoji", "📍")
            description = state.get("description")  # May be None if skipped
            
            # Get largest photo
            photos = message.get("photo", [])
            if not photos:
                return {"ok": False, "error": "no_photo"}
            
            largest = max(photos, key=lambda x: x.get("file_size", 0))
            file_id = largest.get("file_id")
            
            # Get photo URL via Telegram API
            bot_token = os.environ.get('TG_BOT_TOKEN', '')
            photo_url = None
            if bot_token:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                    if resp.status_code == 200:
                        file_path = resp.json().get("result", {}).get("file_path")
                        if file_path:
                            photo_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            
            if not photo_url:
                await self.send_message(chat_id, "❌ Помилка завантаження фото", self.keyboard.main_menu())
                USER_STATES.pop(actor_id, None)
                return {"ok": False, "error": "photo_upload_failed"}
            
            # Create signal with photo
            return await self._create_detailed_signal(chat_id, actor_id, event_type, description, photo_url)
        
        # Handle waiting_content state (photo mode from report flow)
        if state and state.get("step") == "waiting_content":
            # Photo mode: user can send photo with or without caption
            event_type = state.get("signalType")
            event_emoji = state.get("event_emoji", "📍")
            
            # Get largest photo
            photos = message.get("photo", [])
            if not photos:
                return {"ok": False, "error": "no_photo"}
            
            largest = max(photos, key=lambda x: x.get("file_size", 0))
            file_id = largest.get("file_id")
            
            # Get photo URL via Telegram API
            bot_token = os.environ.get('TG_BOT_TOKEN', '')
            photo_url = None
            if bot_token:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                    if resp.status_code == 200:
                        file_path = resp.json().get("result", {}).get("file_path")
                        if file_path:
                            photo_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            
            if not photo_url:
                await self.send_message(chat_id, "❌ Помилка завантаження фото", self.keyboard.main_menu())
                USER_STATES.pop(actor_id, None)
                return {"ok": False, "error": "photo_upload_failed"}
            
            # Check if user has location
            location = await self.location_service.get_location(actor_id)
            
            if not location:
                # Save photo and caption, wait for location
                USER_STATES[actor_id] = {
                    "step": "waiting_location_detailed",
                    "signalType": event_type,
                    "event_emoji": event_emoji,
                    "description": caption if caption else None,
                    "photoUrl": photo_url,
                    "mode": "photo"
                }
                
                await self.send_message(
                    chat_id=chat_id,
                    text="📍 Надішліть локацію для сигналу:",
                    reply_markup=self.keyboard.location_request()
                )
                return {"ok": True, "step": "waiting_location_detailed"}
            
            # Create signal with photo and optional caption
            result = await create_user_report(
                self.db,
                actor_id=actor_id,
                event_type=event_type,
                lat=location["lat"],
                lng=location["lng"],
                username=user_data.get("username"),
                photo_url=photo_url,
                description=caption if caption else None
            )
            
            USER_STATES.pop(actor_id, None)
            
            if result.get("ok"):
                await update_radar_score(self.db, actor_id, 8 if photo_url else 5, "report_with_photo")
                text = f"{event_emoji} Сигнал з фото надіслано ✔"
                await self.send_message(chat_id, text, self.keyboard.main_menu())
            else:
                await self.send_message(chat_id, "❌ Помилка", self.keyboard.main_menu())
            
            return result
        
        # NEW: Handle waiting_photo_step2 - STEP 2 of step-by-step flow
        if state and state.get("step") == "waiting_photo_step2":
            event_type = state.get("signalType")
            event_emoji = state.get("event_emoji", "📍")
            description = state.get("description")  # Already saved in step 1
            
            # Get largest photo
            photos = message.get("photo", [])
            if not photos:
                return {"ok": False, "error": "no_photo"}
            
            largest = max(photos, key=lambda x: x.get("file_size", 0))
            file_id = largest.get("file_id")
            
            # Get photo URL via Telegram API
            bot_token = os.environ.get('TG_BOT_TOKEN', '')
            photo_url = None
            if bot_token:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                    if resp.status_code == 200:
                        file_path = resp.json().get("result", {}).get("file_path")
                        if file_path:
                            photo_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
            
            if not photo_url:
                await self.send_message(chat_id, "❌ Помилка завантаження фото", self.keyboard.main_menu())
                USER_STATES.pop(actor_id, None)
                return {"ok": False, "error": "photo_upload_failed"}
            
            # Create signal with description and photo
            return await self._create_detailed_signal(chat_id, actor_id, event_type, description, photo_url)
        
        # Legacy: waiting_photo state
        if not state or state.get("step") != "waiting_photo":
            # Not in report flow, ignore
            return {"ok": True, "handled": False}
        
        # Get largest photo
        photos = message.get("photo", [])
        if not photos:
            return {"ok": False, "error": "no_photo"}
        
        # Get file_id of largest photo
        largest = max(photos, key=lambda x: x.get("file_size", 0))
        file_id = largest.get("file_id")
        
        # Get photo URL via Telegram API
        bot_token = os.environ.get('TG_BOT_TOKEN', '')
        if bot_token:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                if resp.status_code == 200:
                    file_path = resp.json().get("result", {}).get("file_path")
                    if file_path:
                        photo_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
                        
                        # Check if this is new detailed flow
                        event_type = state.get("signalType")
                        description = state.get("description") or caption  # Use caption as fallback
                        
                        if event_type:
                            # New flow - create signal with photo
                            return await self._create_detailed_signal(
                                chat_id, actor_id, event_type, description, photo_url
                            )
                        else:
                            # Legacy flow
                            return await handle_photo_message(
                                self.db, chat_id, actor_id, photo_url, 
                                user_data.get("username")
                            )
        
        return {"ok": False, "error": "failed_to_get_photo"}
    
    # ==================== Button Handler ====================
    
    async def _handle_button(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle reply keyboard button presses - NEW 3-button UI"""
        from .report_bot import USER_STATES
        from .report_ingestion import create_user_report, update_radar_score
        
        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user_data = message.get("from", {})
        actor_id = f"tg_{chat_id}"
        
        # Check if user is in report flow
        state = USER_STATES.get(actor_id, {})
        
        # NEW: Handle waiting_description_first - STEP 1 of photo mode
        if state.get("step") == "waiting_description_first":
            event_type = state.get("signalType")
            event_emoji = state.get("event_emoji", "📍")
            
            # Skip cancel/back buttons
            if text and not text.startswith("❌") and not text.startswith("↩️"):
                # Save description and ask for photo
                USER_STATES[actor_id] = {
                    "step": "waiting_photo_optional",
                    "signalType": event_type,
                    "event_emoji": event_emoji,
                    "description": text,
                    "mode": "photo"
                }
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📷 Додати фото", "callback_data": f"wait_photo:{event_type}"}],
                        [{"text": "✅ Відправити без фото", "callback_data": f"send_with_desc:{event_type}"}],
                        [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                    ]
                }
                
                await self.send_message(
                    chat_id=chat_id,
                    text=f"📝 Опис: _{text[:100]}{'...' if len(text) > 100 else ''}_\n\nКрок 2: Додати фото?",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return {"ok": True, "step": "waiting_photo_optional"}
        
        # Handle waiting_content state - user sends text only (no photo)
        if state.get("step") == "waiting_content":
            event_type = state.get("signalType")
            event_emoji = state.get("event_emoji", "📍")
            
            # Skip cancel button
            if text and not text.startswith("❌") and not text.startswith("↩️"):
                # Check if user has location
                location = await self.location_service.get_location(actor_id)
                
                if not location:
                    # Save description, wait for location
                    USER_STATES[actor_id] = {
                        "step": "waiting_location_detailed",
                        "signalType": event_type,
                        "event_emoji": event_emoji,
                        "description": text,
                        "photoUrl": None,
                        "mode": "photo"
                    }
                    
                    await self.send_message(
                        chat_id=chat_id,
                        text="📍 Надішліть локацію для сигналу:",
                        reply_markup=self.keyboard.location_request()
                    )
                    return {"ok": True, "step": "waiting_location_detailed"}
                
                # Create signal with text only
                result = await create_user_report(
                    self.db,
                    actor_id=actor_id,
                    event_type=event_type,
                    lat=location["lat"],
                    lng=location["lng"],
                    username=user_data.get("username"),
                    description=text
                )
                
                USER_STATES.pop(actor_id, None)
                
                if result.get("ok"):
                    await update_radar_score(self.db, actor_id, 5, "new_report")
                    text_resp = f"{event_emoji} Сигнал надіслано ✔"
                    await self.send_message(chat_id, text_resp, self.keyboard.main_menu())
                else:
                    await self.send_message(chat_id, "❌ Помилка", self.keyboard.main_menu())
                
                return result
        
        # Handle waiting_description state (legacy)
        if state.get("step") == "waiting_description":
            # User sent description text
            event_type = state.get("signalType")
            if text and not text.startswith("❌") and not text.startswith("↩️"):
                # Save description and ask for photo or send
                USER_STATES[actor_id] = {
                    "step": "waiting_photo_or_send",
                    "signalType": event_type,
                    "description": text
                }
                
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "📷 Додати фото", "callback_data": f"add_photo:{event_type}"}],
                        [{"text": "✅ Відправити без фото", "callback_data": f"send_no_photo:{event_type}"}],
                        [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                    ]
                }
                
                await self.send_message(
                    chat_id=chat_id,
                    text=f"📝 Опис збережено:\n_{text[:100]}{'...' if len(text) > 100 else ''}_\n\nДодати фото?",
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return {"ok": True, "action": "description_saved"}
        
        # NEW Main menu - 3 buttons only
        button_handlers = {
            # Primary 3 buttons
            "➕ Повідомити": self.cmd_report_new,
            "📡 Радар": self._show_radar_screen,
            "👤 Профіль": self._show_profile_screen,
            # Back button
            "↩️ Назад": self._show_main_menu,
            # Cancel
            "❌ Скасувати": self._cancel_and_back,
            # Legacy compat
            "📊 Статус": self._show_profile_screen,
            "⚙️ Меню": self._show_settings_screen,
            "📍 Локація": self.cmd_location,
            "🚨 Повідомити": self.cmd_report_new,
            "📡 Повідомити": self.cmd_report_new,
            "💰 Заробити": self._show_earnings_screen,
        }
        
        handler = button_handlers.get(text)
        if handler:
            return await handler(chat_id, user_data)
        
        return {"ok": True, "handled": False}
    
    async def _cancel_and_back(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Cancel current operation and return to main menu"""
        from .report_bot import USER_STATES
        
        actor_id = f"tg_{chat_id}"
        USER_STATES.pop(actor_id, None)
        
        await self.send_message(
            chat_id=chat_id,
            text="❌",
            reply_markup=self.keyboard.main_menu()
        )
        return {"ok": True, "action": "cancelled"}
    
    # ==================== NEW SCREENS ====================
    
    async def _show_radar_screen(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """📡 Радар - Show radar status screen"""
        actor_id = f"tg_{chat_id}"
        settings = await self.settings_service.get_or_create_settings(actor_id)
        location = await self.location_service.get_location(actor_id)
        
        is_enabled = settings.get("radarEnabled", False)
        radius = settings.get("radius", 1000)
        location_mode = settings.get("locationMode", "15m")
        
        # Mode labels
        mode_labels = {
            "5m": "5 хв",
            "15m": "15 хв", 
            "1h": "1 година",
            "1d": "24 години",
            "permanent": "24 години (авто)",
            "none": "не зберігається"
        }
        ttl_label = mode_labels.get(location_mode, location_mode)
        
        if is_enabled and location:
            text = (
                "📡 *Радар активний*\n\n"
                f"📍 Радіус: {radius} м\n"
                f"⏱ Час дії: {ttl_label}\n\n"
                "🔒 Локація буде видалена після завершення"
            )
        elif location:
            text = (
                "📡 *Радар вимкнено*\n\n"
                f"📍 Локація: збережена\n"
                f"📏 Радіус: {radius} м"
            )
        else:
            text = (
                "📡 *Радар*\n\n"
                "📍 Надішліть локацію для активації"
            )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.radar_menu(is_enabled, radius, ttl_label),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "radar_screen"}
    
    async def _show_profile_screen(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """👤 Профіль - Show profile screen"""
        from .report_ingestion import get_user_stats
        from .referral_service import ReferralService
        
        actor_id = f"tg_{chat_id}"
        
        # Get settings
        settings = await self.settings_service.get_or_create_settings(actor_id)
        location = await self.location_service.get_location(actor_id)
        
        # Get user stats
        user_stats = await get_user_stats(self.db, actor_id)
        
        # Get referral data
        ref_svc = ReferralService(self.db)
        ref_stats = await ref_svc.get_user_referral_stats(actor_id)
        
        radar_status = "ON" if settings.get("radarEnabled") else "OFF"
        radius = settings.get("radius", 1000)
        reports_total = user_stats.get("reportsTotal", 0) if user_stats.get("ok") else 0
        
        balance = ref_stats.get("balance", 0) if ref_stats.get("ok") else 0
        referrals_count = ref_stats.get("totalReferrals", 0) if ref_stats.get("ok") else 0
        
        text = (
            "👤 *Ваш профіль*\n\n"
            f"📡 Радар: {radar_status}\n"
            f"📍 Радіус: {radius} м\n"
            f"📊 Надіслано сигналів: {reports_total}\n\n"
            f"💰 Баланс: ${balance:.2f}\n"
            f"👥 Запрошено: {referrals_count}"
        )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.profile_menu(),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "profile_screen"}
    
    async def _show_earnings_screen(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """💰 Заробіток - Show earnings screen with rewards integration"""
        from .referral_service import ReferralService
        from .rewards_service import RewardsService
        
        actor_id = f"tg_{chat_id}"
        
        # Get referral stats
        ref_svc = ReferralService(self.db)
        ref_stats = await ref_svc.get_user_referral_stats(actor_id)
        
        ref_balance = ref_stats.get("balance", 0) if ref_stats.get("ok") else 0
        referrals_count = ref_stats.get("totalReferrals", 0) if ref_stats.get("ok") else 0
        active_referrals = ref_stats.get("activeReferrals", 0) if ref_stats.get("ok") else 0
        ref_link = ref_stats.get("referralLink", f"t.me/ARKHOR_bot?start=ref_{chat_id}") if ref_stats.get("ok") else f"t.me/ARKHOR_bot?start=ref_{chat_id}"
        
        # Get rewards balance
        rewards_svc = RewardsService(self.db)
        rewards_balance = await rewards_svc.get_balance(actor_id)
        
        rewards_usd = rewards_balance["balance"]
        rewards_stars = rewards_balance["balanceStars"]
        total_earned = rewards_balance["totalEarned"]
        
        # Combined balance
        total_balance = ref_balance + rewards_usd
        
        text = (
            "💰 *Заробіток*\n\n"
            f"📊 *Загальний баланс: ${total_balance:.2f}*\n\n"
            f"🎯 За сигнали: ${rewards_usd:.2f} ({rewards_stars} ⭐)\n"
            f"👥 За рефералів: ${ref_balance:.2f}\n\n"
            f"📈 Всього зароблено: ${total_earned + ref_balance:.2f}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "💡 *Як заробляти:*\n\n"
            "📍 *За сигнали:*\n"
            "• $0.30 базова за сигнал\n"
            "• +$0.10 бонус за фото\n"
            "• +$0.10 бонус за ⚡Миттєво (точна геолокація)\n"
            "• $0.05 за підтвердження чужого\n"
            "• +$0.15 бонус за 3 дні поспіль\n\n"
            "👥 *Реферальна програма:*\n"
            f"• 30% від підписки друга ($0.60)\n"
            f"• Запрошено: {referrals_count} (активних: {active_referrals})\n\n"
            f"🔗 Ваше посилання:\n`{ref_link}`"
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "📜 Історія нарахувань", "callback_data": "rewards_history"}],
                [{"text": "🏆 Топ заробітку", "callback_data": "rewards_leaderboard"}],
            ]
        }
        
        if rewards_balance["canWithdraw"] or ref_balance >= 1.0:
            keyboard["inline_keyboard"].append([{"text": "💸 Вивести", "callback_data": "rewards_withdraw"}])
        
        keyboard["inline_keyboard"].append([{"text": "↩️ Назад", "callback_data": "menu_back"}])
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "earnings_screen"}
    
    async def _show_settings_screen(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """⚙️ Налаштування - Show settings screen"""
        await self.send_message(
            chat_id=chat_id,
            text="⚙️ *Налаштування*",
            reply_markup=self.keyboard.settings_menu(),
            parse_mode="Markdown"
        )
        return {"ok": True, "action": "settings_screen"}
    
    async def _show_location_settings(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """📍 Налаштування локації - with privacy disclaimer"""
        actor_id = f"tg_{chat_id}"
        settings = await self.settings_service.get_or_create_settings(actor_id)
        current_mode = settings.get("locationMode", "15m")
        
        text = (
            "📍 *Налаштування локації*\n\n"
            "Ви обираєте, як довго система може використовувати вашу локацію.\n\n"
            "🔒 Локація:\n"
            "• не зберігається постійно\n"
            "• автоматично видаляється після завершення таймера\n"
            "• використовується тільки для сигналів поруч"
        )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.location_ttl_options(current_mode),
            parse_mode="Markdown"
        )
        return {"ok": True, "action": "location_settings"}
    
    async def _show_subscription_screen(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """⭐ Підписка - Show subscription screen"""
        from .telegram_stars_payment import SubscriptionService
        
        actor_id = f"tg_{chat_id}"
        sub_svc = SubscriptionService(self.db)
        sub = await sub_svc.get_subscription(actor_id)
        
        is_active = sub and sub.get("status") == "active"
        
        if is_active:
            expires = sub.get("expiresAt", "")
            if isinstance(expires, datetime):
                expires_str = expires.strftime("%d.%m.%Y")
            else:
                expires_str = str(expires)[:10]
            
            text = (
                "⭐ *Підписка*\n\n"
                "План: Premium\n"
                "Статус: ✅ Активний\n"
                f"До: {expires_str}\n\n"
                "Ціна: $1 / місяць"
            )
        else:
            text = (
                "⭐ *Підписка*\n\n"
                "План: Basic\n"
                "Статус: Безкоштовний\n\n"
                "Premium ($1/міс):\n"
                "• Без реклами\n"
                "• Розширений радіус\n"
                "• Пріоритетні сповіщення"
            )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.subscription_menu(is_active),
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "subscription_screen"}
    
    # Legacy compatibility
    async def cmd_status_full(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Redirect to profile screen"""
        return await self._show_profile_screen(chat_id, user_data)
    
    async def _show_extended_menu(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Redirect to settings screen"""
        return await self._show_settings_screen(chat_id, user_data)
    
    async def _show_radar_toggle(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Redirect to radar screen"""
        return await self._show_radar_screen(chat_id, user_data)
    
    async def _show_main_menu(self, chat_id: int, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Show main menu"""
        await self.send_message(
            chat_id=chat_id,
            text="Головне меню:",
            reply_markup=self.keyboard.main_menu()
        )
        
        return {"ok": True, "action": "main_menu"}
    
    # ==================== Callback Handler ====================
    
    async def _handle_callback(self, callback_query: Dict[str, Any]) -> Dict[str, Any]:
        """Handle inline button callbacks"""
        callback_id = callback_query["id"]
        chat_id = callback_query["message"]["chat"]["id"]
        data = callback_query.get("data", "")
        actor_id = f"tg_{chat_id}"
        
        # Radar toggle
        if data == "radar_on":
            return await self.cmd_radar_on(chat_id, callback_query.get("from", {}))
        
        if data == "radar_off":
            return await self.cmd_radar_off(chat_id, callback_query.get("from", {}))
        
        # Radius selection
        if data.startswith("radius_"):
            radius = int(data.replace("radius_", ""))
            await self.settings_service.set_radius(actor_id, radius)
            
            await self.send_message(
                chat_id=chat_id,
                text=f"🎯 Радіус встановлено: *{radius} м*",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "radius_set", "radius": radius}
        
        # Event type toggle
        if data.startswith("type_"):
            event_type = data.replace("type_", "")
            result = await self.settings_service.toggle_event_type(actor_id, event_type)
            
            settings = await self.settings_service.get_settings(actor_id)
            
            await self.send_message(
                chat_id=chat_id,
                text="🧩 Виберіть типи сигналів:",
                reply_markup=self.keyboard.event_types(settings.get("eventTypes", []))
            )
            return {"ok": True, "action": "type_toggled", "type": event_type}
        
        # Sensitivity
        if data.startswith("sens_"):
            sensitivity = data.replace("sens_", "")
            await self.settings_service.set_sensitivity(actor_id, sensitivity)
            
            await self.send_message(
                chat_id=chat_id,
                text=f"📶 Чутливість: *{sensitivity}*",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "sensitivity_set"}
        
        # Quiet hours
        if data == "quiet_on":
            await self.settings_service.set_quiet_hours(actor_id, True)
            await self.send_message(
                chat_id=chat_id,
                text="🌙 Тихі години *увімкнено* (23:00 - 07:00)",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "quiet_on"}
        
        if data == "quiet_off":
            await self.settings_service.set_quiet_hours(actor_id, False)
            await self.send_message(
                chat_id=chat_id,
                text="🔔 Тихі години *вимкнено*",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "quiet_off"}
        
        # Settings menu navigation
        if data == "menu_radius":
            return await self.cmd_radius(chat_id, {})
        
        if data == "menu_types":
            return await self.cmd_types(chat_id, {})
        
        if data == "menu_nearby":
            return await self.cmd_nearby(chat_id, {})
        
        if data == "menu_leaderboard":
            return await self.cmd_leaderboard(chat_id, {})
        
        if data == "menu_location":
            return await self.cmd_location(chat_id, {})
        
        # NEW: Location settings with privacy disclaimer
        if data == "menu_location_settings":
            return await self._show_location_settings(chat_id, {})
        
        if data == "menu_help":
            return await self.cmd_help(chat_id, {})
        
        if data == "menu_back":
            return await self._show_main_menu(chat_id, {})
        
        # NEW: Profile menu navigation
        if data == "menu_earnings":
            return await self._show_earnings_screen(chat_id, {})
        
        if data == "menu_subscribe":
            return await self._show_subscription_screen(chat_id, {})
        
        if data == "menu_settings":
            return await self._show_settings_screen(chat_id, {})
        
        if data == "back_profile":
            return await self._show_profile_screen(chat_id, {})
        
        if data == "back_radar":
            return await self._show_radar_screen(chat_id, {})
        
        # Share referral link
        if data == "share_referral":
            ref_code = f"ref_{chat_id}"
            ref_link = f"t.me/ARKHOR_bot?start={ref_code}"
            
            await self.send_message(
                chat_id=chat_id,
                text=f"👥 *Запросіть друзів*\n\nВаше посилання:\n`{ref_link}`\n\n"
                     f"Отримуйте $0.30 за кожного активного користувача!",
                reply_markup=self.keyboard.back_button("back_profile"),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "share_referral"}
        
        if data == "menu_sensitivity":
            settings = await self.settings_service.get_settings(actor_id)
            await self.send_message(
                chat_id=chat_id,
                text="📶 Виберіть чутливість:",
                reply_markup=self.keyboard.sensitivity_options(settings.get("sensitivity", "medium"))
            )
            return {"ok": True, "action": "show_sensitivity"}
        
        if data == "menu_quiet":
            settings = await self.settings_service.get_settings(actor_id)
            quiet = settings.get("quietHours", {})
            await self.send_message(
                chat_id=chat_id,
                text="🌙 Тихі години (23:00 - 07:00):",
                reply_markup=self.keyboard.quiet_hours_toggle(quiet.get("enabled", False))
            )
            return {"ok": True, "action": "show_quiet"}
        
        # ==================== Geo Session TTL ====================
        
        if data == "menu_location_settings":
            # Show location TTL options
            settings = await self.settings_service.get_settings(actor_id)
            current_mode = settings.get("locationMode", "15m") if settings else "15m"
            
            await self.send_message(
                chat_id=chat_id,
                text="📍 *Налаштування локації*\n\nЯк довго використовувати вашу локацію?\n\n"
                     "🔒 Ваша локація автоматично видаляється після завершення таймера.",
                reply_markup=self.keyboard.location_ttl_options(current_mode),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "show_location_settings"}
        
        if data.startswith("location_ttl:"):
            mode = data.replace("location_ttl:", "")
            
            # Save mode preference
            await self.settings_service.update_settings(actor_id, {"locationMode": mode})
            
            # Mode labels
            mode_labels = {
                "5m": "5 хвилин",
                "15m": "15 хвилин",
                "1h": "1 година",
                "1d": "1 день",
                "permanent": "Постійно (оновлення щодня)",
                "none": "Не зберігати"
            }
            
            mode_label = mode_labels.get(mode, mode)
            
            if mode == "none":
                # Delete existing session
                from .geo_session_service import GeoSessionService
                session_svc = GeoSessionService(self.db)
                await session_svc.delete_session(actor_id)
                
                await self.send_message(
                    chat_id=chat_id,
                    text="🔒 *Режим приватності*\n\nЛокація не зберігається.\n"
                         "Для отримання сповіщень надсилайте локацію кожного разу.",
                    reply_markup=self.keyboard.main_menu(),
                    parse_mode="Markdown"
                )
            else:
                # Request location to create session
                await self.send_message(
                    chat_id=chat_id,
                    text=f"📍 Режим: *{mode_label}*\n\nНадішліть локацію для активації радара:",
                    reply_markup=self.keyboard.location_request(),
                    parse_mode="Markdown"
                )
            
            return {"ok": True, "action": "location_mode_set", "mode": mode}
        
        if data.startswith("extend_session:"):
            minutes = int(data.replace("extend_session:", ""))
            
            from .geo_session_service import GeoSessionService
            session_svc = GeoSessionService(self.db)
            session = await session_svc.extend_session(actor_id, minutes)
            
            if session:
                remaining = int((session["expiresAt"] - datetime.now(timezone.utc)).total_seconds() / 60)
                await self.send_message(
                    chat_id=chat_id,
                    text=f"✅ Радар продовжено!\n\n⏱ Залишилось: {remaining} хв",
                    reply_markup=self.keyboard.main_menu()
                )
            else:
                await self.send_message(
                    chat_id=chat_id,
                    text="❌ Немає активної сесії. Надішліть локацію:",
                    reply_markup=self.keyboard.location_request()
                )
            
            return {"ok": True, "action": "session_extended", "minutes": minutes}
        
        if data == "session_disable":
            from .geo_session_service import GeoSessionService
            session_svc = GeoSessionService(self.db)
            await session_svc.delete_session(actor_id)
            await self.settings_service.set_radar_enabled(actor_id, False)
            
            await self.send_message(
                chat_id=chat_id,
                text="🚫 *Радар вимкнено*\n\n🔒 Вашу локацію видалено.",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "session_disabled"}
        
        if data == "session_refresh":
            # Refresh permanent session
            location = await self.location_service.get_location(actor_id)
            if location:
                from .geo_session_service import GeoSessionService
                settings = await self.settings_service.get_settings(actor_id)
                session_svc = GeoSessionService(self.db)
                
                await session_svc.create_session(
                    user_id=actor_id,
                    lat=location["lat"],
                    lng=location["lng"],
                    radius=settings.get("radius", 1000) if settings else 1000,
                    mode="permanent"
                )
                
                await self.send_message(
                    chat_id=chat_id,
                    text="🔄 *Зону оновлено*\n\n📡 Радар активний ще 24 години.",
                    reply_markup=self.keyboard.main_menu(),
                    parse_mode="Markdown"
                )
            else:
                await self.send_message(
                    chat_id=chat_id,
                    text="📍 Надішліть локацію:",
                    reply_markup=self.keyboard.location_request()
                )
            
            return {"ok": True, "action": "session_refreshed"}
        
        # ==================== End Geo Session ====================
        
        if data == "remove_location":
            # Remove user location
            await self.location_service.delete_location(actor_id)
            await self.settings_service.set_radar_enabled(actor_id, False)
            await self.user_service.update_state(actor_id, "PAUSED")
            
            await self.send_message(
                chat_id=chat_id,
                text="📍 *Локацію видалено*\n\nВи більше не будете отримувати proximity alerts.\n\nЩоб відновити, надішліть нову локацію.",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "location_removed"}
        
        if data == "reset_settings":
            # Reset to defaults
            from .bot_settings_service import DEFAULT_SETTINGS
            await self.settings_service.update_settings(actor_id, DEFAULT_SETTINGS)
            
            await self.send_message(
                chat_id=chat_id,
                text="🗑 *Налаштування скинуто*\n\nВсі налаштування повернено до значень за замовчуванням.",
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "settings_reset"}
        
        if data == "cancel":
            await self.send_message(
                chat_id=chat_id,
                text="Скасовано",
                reply_markup=self.keyboard.main_menu()
            )
            return {"ok": True, "action": "cancelled"}
        
        # NEW: Mode selection callbacks (instant or photo)
        if data == "mode_instant":
            from .report_bot import handle_mode_callback
            message_id = callback_query["message"]["message_id"]
            return await handle_mode_callback(self.db, chat_id, message_id, actor_id, "instant")
        
        if data == "mode_photo":
            from .report_bot import handle_mode_callback
            message_id = callback_query["message"]["message_id"]
            return await handle_mode_callback(self.db, chat_id, message_id, actor_id, "photo")
        
        # NEW: Skip to photo callback
        if data.startswith("skip_to_photo:"):
            event_type = data.split(":")[1]
            return await self._handle_skip_to_photo(chat_id, actor_id, event_type)
        
        # NEW: Skip description in step-by-step flow
        if data.startswith("skip_desc:"):
            event_type = data.split(":")[1]
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            USER_STATES[actor_id] = {
                **state,
                "step": "waiting_photo_optional",
                "signalType": event_type,
                "description": None
            }
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📷 Додати фото", "callback_data": f"wait_photo:{event_type}"}],
                    [{"text": "✅ Відправити без опису і фото", "callback_data": f"send_empty:{event_type}"}],
                    [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                ]
            }
            await self.send_message(chat_id, "Крок 2: Додати фото?", keyboard)
            return {"ok": True, "step": "waiting_photo_optional"}
        
        # NEW: Wait for photo (step 2)
        if data.startswith("wait_photo:"):
            event_type = data.split(":")[1]
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            USER_STATES[actor_id] = {
                **state,
                "step": "waiting_photo_step2",
                "signalType": event_type
            }
            await self.send_message(
                chat_id=chat_id,
                text="📷 Надішліть фото:",
                reply_markup={"inline_keyboard": [
                    [{"text": "⏭ Пропустити", "callback_data": f"send_with_desc:{event_type}"}],
                    [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                ]}
            )
            return {"ok": True, "step": "waiting_photo_step2"}
        
        # NEW: Send with description (no photo)
        if data.startswith("send_with_desc:"):
            event_type = data.split(":")[1]
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            description = state.get("description")
            event_emoji = state.get("event_emoji", "📍")
            return await self._create_detailed_signal(chat_id, actor_id, event_type, description, None)
        
        # NEW: Send without description and photo
        if data.startswith("send_empty:"):
            event_type = data.split(":")[1]
            return await self._create_detailed_signal(chat_id, actor_id, event_type, None, None)
        
        # NEW: Fast report type selection (Waze-style)
        if data.startswith("report_type:"):
            event_type = data.split(":")[1]
            from .report_bot import handle_report_type_callback
            message_id = callback_query["message"]["message_id"]
            return await handle_report_type_callback(self.db, chat_id, message_id, actor_id, event_type)
        
        # Report event callbacks
        if data.startswith("report_"):
            event_type = data.replace("report_", "")
            return await self._handle_report_type(chat_id, actor_id, event_type)
        
        # NEW: Instant send callback
        if data.startswith("send_instant:"):
            event_type = data.split(":")[1]
            return await self._handle_instant_send(chat_id, actor_id, event_type)
        
        # NEW: Detailed send callback (with description/photo)
        if data.startswith("send_detailed:"):
            event_type = data.split(":")[1]
            return await self._handle_detailed_send(chat_id, actor_id, event_type)
        
        # NEW: Skip description callback
        if data.startswith("skip_description:"):
            event_type = data.split(":")[1]
            return await self._handle_skip_description(chat_id, actor_id, event_type)
        
        # NEW: Add photo callback
        if data.startswith("add_photo:"):
            event_type = data.split(":")[1]
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            USER_STATES[actor_id] = {
                **state,
                "step": "waiting_photo",
                "signalType": event_type
            }
            await self.send_message(
                chat_id=chat_id,
                text="📷 Надішліть фото:",
                reply_markup={"inline_keyboard": [
                    [{"text": "⏭ Пропустити фото", "callback_data": f"send_no_photo:{event_type}"}],
                    [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                ]}
            )
            return {"ok": True, "action": "waiting_photo"}
        
        # NEW: Send without photo callback
        if data.startswith("send_no_photo:") or data.startswith("send_without_photo:"):
            event_type = data.split(":")[1]
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            description = state.get("description")
            return await self._create_detailed_signal(chat_id, actor_id, event_type, description, None)
        
        # NEW: Photo option callback
        if data.startswith("report_photo:"):
            action = data.split(":")[1]
            from .report_bot import handle_photo_callback
            message_id = callback_query["message"]["message_id"]
            username = callback_query.get("from", {}).get("username")
            return await handle_photo_callback(self.db, chat_id, message_id, actor_id, action, username)
        
        # NEW: Confirm/reject crowd signal (single)
        if data.startswith("confirm:"):
            parts = data.split(":")
            if len(parts) >= 3:
                report_id = parts[1]
                action = parts[2]
                message_id = callback_query["message"]["message_id"]
                return await self._handle_signal_confirmation(chat_id, message_id, actor_id, report_id, action)
        
        # NEW: Confirm/reject batch signals
        if data.startswith("confirm_batch:"):
            parts = data.split(":")
            if len(parts) >= 3:
                batch_id = parts[1]
                action = parts[2]
                message_id = callback_query["message"]["message_id"]
                return await self._handle_signal_confirmation(chat_id, message_id, actor_id, batch_id, action, is_batch=True)
        
        # Confirm/deny event
        if data.startswith("confirm_"):
            event_id = data.replace("confirm_", "")
            return await self._handle_confirm_event(chat_id, actor_id, event_id, True)
        
        if data.startswith("deny_"):
            event_id = data.replace("deny_", "")
            return await self._handle_confirm_event(chat_id, actor_id, event_id, False)
        
        # Mute event
        if data.startswith("mute_"):
            return await self._handle_mute(chat_id, actor_id, data)
        
        # ==================== Referral Callbacks ====================
        
        if data == "ref_withdraw":
            from .referral_bot import handle_withdraw_command
            return await handle_withdraw_command(self.db, chat_id, actor_id)
        
        if data == "menu_referrals":
            from .referral_bot import handle_referrals_command
            return await handle_referrals_command(self.db, chat_id, actor_id)
        
        if data == "menu_help":
            return await self.cmd_help(chat_id, {"id": int(actor_id.replace("tg_", ""))})
        
        if data == "ref_leaderboard":
            from .referral_bot import handle_referral_leaderboard
            return await handle_referral_leaderboard(self.db, chat_id)
        
        if data == "ref_history":
            from .referral_bot import handle_referral_history
            return await handle_referral_history(self.db, chat_id, actor_id)
        
        if data.startswith("withdraw_"):
            # withdraw_ton:10.50 or withdraw_usdt:10.50 or withdraw_stars:10.50
            parts = data.replace("withdraw_", "").split(":")
            if len(parts) == 2:
                method = parts[0]
                amount = float(parts[1])
                from .referral_bot import handle_withdraw_callback
                message_id = callback_query["message"]["message_id"]
                return await handle_withdraw_callback(self.db, chat_id, message_id, actor_id, method, amount)
        
        if data == "cancel_withdraw":
            # Cancel withdrawal flow
            await self.db.user_states.delete_one({"userId": actor_id})
            await self.send_message(
                chat_id=chat_id,
                text="❌ Виведення скасовано",
                reply_markup=self.keyboard.main_menu()
            )
            return {"ok": True, "action": "withdraw_cancelled"}
        
        if data == "subscribe_pay" or data == "subscribe_extend":
            from .referral_bot import handle_subscribe_callback
            return await handle_subscribe_callback(self.db, chat_id, actor_id)
        
        # Subscription with Telegram Stars
        if data == "subscribe_monthly":
            from .telegram_stars_payment import TelegramStarsPaymentService
            payment_svc = TelegramStarsPaymentService(self.db)
            result = await payment_svc.send_invoice(chat_id, actor_id, "monthly")
            return {"ok": result.get("ok", False), "action": "invoice_sent"}
        
        if data == "subscribe_yearly":
            from .telegram_stars_payment import TelegramStarsPaymentService
            payment_svc = TelegramStarsPaymentService(self.db)
            result = await payment_svc.send_invoice(chat_id, actor_id, "yearly")
            return {"ok": result.get("ok", False), "action": "invoice_sent"}
        
        # ==================== Admin Moderation ====================
        
        if data.startswith("admin_approve:"):
            signal_id = data.replace("admin_approve:", "")
            return await self._handle_admin_approve(chat_id, callback_query, signal_id)
        
        if data.startswith("admin_reject:"):
            signal_id = data.replace("admin_reject:", "")
            return await self._handle_admin_reject(chat_id, callback_query, signal_id)
        
        if data.startswith("admin_ban:"):
            signal_id = data.replace("admin_ban:", "")
            return await self._handle_admin_ban(chat_id, callback_query, signal_id)
        
        # ==================== Location Mode Selection ====================
        
        if data == "location_mode:current":
            # Use current location - show location request
            await self.send_message(
                chat_id=chat_id,
                text="📍 Надішліть свою локацію:",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": True, "action": "location_mode_current"}
        
        if data == "location_mode:map":
            # Open map picker
            from .map_location_picker import MapLocationPickerService
            picker_svc = MapLocationPickerService(self.db)
            
            # Get signal type from user state if available
            from .report_bot import USER_STATES
            state = USER_STATES.get(actor_id, {})
            signal_type = state.get("signalType")
            
            result = await picker_svc.create_picker_token(actor_id, signal_type, chat_id)
            
            if result.get("ok"):
                await self.send_message(
                    chat_id=chat_id,
                    text="🗺 *Виберіть точку на карті*\n\nНатисніть кнопку нижче, щоб відкрити карту:",
                    reply_markup=picker_svc.get_map_picker_button(result["webappUrl"]),
                    parse_mode="Markdown"
                )
            return {"ok": True, "action": "location_mode_map"}
        
        # ==================== Rewards Balance ====================
        
        if data == "rewards_history":
            from .rewards_service import RewardsService
            rewards_svc = RewardsService(self.db)
            history = await rewards_svc.get_transaction_history(actor_id, 10)
            
            if not history:
                text = "📜 *Історія порожня*\n\nПочніть підтверджувати сигнали, щоб заробляти!"
            else:
                lines = ["📜 *Історія нарахувань*\n"]
                for tx in history[:10]:
                    amount = tx.get("amount", 0)
                    tx_type = tx.get("type", "")
                    stars = int(abs(amount) * 50)
                    
                    if tx_type == "signal_created":
                        lines.append(f"✅ Сигнал створено: +{stars} ⭐")
                    elif tx_type == "signal_confirmed":
                        lines.append(f"👁 Підтвердження: +{stars} ⭐")
                    elif tx_type == "confirmation_received":
                        lines.append(f"🎁 Бонус: +{stars} ⭐")
                    elif tx_type == "withdrawal":
                        lines.append(f"💸 Виведення: -{stars} ⭐")
                
                text = "\n".join(lines)
            
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup={"inline_keyboard": [[{"text": "↩️ Назад", "callback_data": "back_earnings"}]]},
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "show_history"}
        
        if data == "rewards_leaderboard":
            from .rewards_service import RewardsService
            rewards_svc = RewardsService(self.db)
            leaders = await rewards_svc.get_top_earners(10)
            
            if not leaders:
                text = "🏆 *Топ ще порожній*"
            else:
                lines = ["🏆 *Топ заробітку*\n"]
                medals = ["🥇", "🥈", "🥉"]
                for i, leader in enumerate(leaders):
                    medal = medals[i] if i < 3 else f"{i+1}."
                    stars = leader.get("totalEarnedStars", 0)
                    lines.append(f"{medal} {stars} ⭐")
                text = "\n".join(lines)
            
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup={"inline_keyboard": [[{"text": "↩️ Назад", "callback_data": "back_earnings"}]]},
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "show_leaderboard"}
        
        if data == "rewards_withdraw":
            from .rewards_service import RewardsService
            rewards_svc = RewardsService(self.db)
            result = await rewards_svc.withdraw(actor_id, "stars")
            
            if result.get("ok"):
                stars = result.get("stars", 0)
                text = f"💸 *Запит на виведення*\n\n{stars} ⭐ буде нараховано найближчим часом."
            else:
                text = f"❌ {result.get('error', 'Помилка')}"
            
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup={"inline_keyboard": [[{"text": "↩️ Назад", "callback_data": "back_earnings"}]]},
                parse_mode="Markdown"
            )
            return {"ok": True, "action": "withdraw"}
        
        if data == "back_earnings":
            return await self._show_earnings_screen(chat_id, {"id": chat_id})
        
        return {"ok": True, "handled": False}
    
    async def _handle_report_type(self, chat_id: int, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Handle report type selection - show send options"""
        from .crowd_signal_service import EVENT_CONFIG
        from .report_bot import USER_STATES
        
        # Save selected type in user state
        USER_STATES[actor_id] = {
            "step": "choose_send_mode",
            "signalType": event_type
        }
        
        config = EVENT_CONFIG.get(event_type, EVENT_CONFIG.get("other", {}))
        icon = config.get("icon", "⚠️")
        label = config.get("label", event_type)
        
        text = (
            f"{icon} *{label}*\n\n"
            "Оберіть спосіб надсилання:"
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "⚡ Відправити миттєво", "callback_data": f"send_instant:{event_type}"}],
                [{"text": "📝 Додати опис та фото", "callback_data": f"send_detailed:{event_type}"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "show_send_options", "eventType": event_type}
    
    async def _handle_instant_send(self, chat_id: int, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Handle instant signal send - requires location
        
        Миттєво = точна геолокація, тому винагорода як за текст + фото ($0.40)
        """
        from .crowd_signal_service import CrowdSignalService, EVENT_CONFIG
        from .report_bot import USER_STATES
        from .trust_score_service import TrustScoreService
        from .admin_moderation_service import AdminModerationService
        
        # Clear user state
        USER_STATES.pop(actor_id, None)
        
        # Check location
        location = await self.location_service.get_location(actor_id)
        if not location:
            # Save state for after location received
            USER_STATES[actor_id] = {
                "step": "waiting_location_instant",
                "signalType": event_type
            }
            await self.send_message(
                chat_id=chat_id,
                text="📍 Надішліть свою локацію для створення сигналу:",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": False, "error": "no_location", "waiting": True}
        
        # Check if moderation required
        trust_svc = TrustScoreService(self.db)
        mod_check = await trust_svc.requires_moderation(actor_id, has_photo=False)
        
        # Create event instantly
        crowd_service = CrowdSignalService(self.db)
        result = await crowd_service.create_event(
            actor_id=actor_id,
            event_type=event_type,
            lat=location["lat"],
            lng=location["lng"]
        )
        
        # Instant = точна геолокація = як текст + фото
        instant_reward = 0.40  # $0.40 (базова $0.30 + бонус за точну геолокацію $0.10)
        
        if result.get("ok"):
            config = EVENT_CONFIG.get(event_type, EVENT_CONFIG.get("other", {}))
            icon = config.get("icon", "⚠️")
            label = config.get("label", event_type)
            
            if mod_check.get("required"):
                # Submit for moderation
                mod_svc = AdminModerationService(self.db)
                await mod_svc.submit_for_moderation(
                    signal_id=result.get("eventId", ""),
                    actor_id=actor_id,
                    signal_type=event_type,
                    text=None,
                    photo_url=None,
                    lat=location["lat"],
                    lng=location["lng"]
                )
                text = (
                    f"📩 *Сигнал надіслано на модерацію*\n\n"
                    f"Дякуємо!\n\n"
                    f"🫡 +${instant_reward:.2f}"
                )
            elif result.get("action") == "merged":
                text = (
                    f"✅ *Сигнал підтверджено*\n\n"
                    f"Дякуємо!\n\n"
                    f"🫡 +$0.05"
                )
            else:
                text = (
                    f"✅ *Сигнал створено*\n\n"
                    f"Дякуємо!\n\n"
                    f"🫡 +${instant_reward:.2f}"
                )
            
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
        else:
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Помилка: {result.get('message', 'Unknown error')}",
                reply_markup=self.keyboard.main_menu()
            )
        
        return result
    
    async def _handle_detailed_send(self, chat_id: int, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Handle detailed signal - ask for description and photo"""
        from .crowd_signal_service import EVENT_CONFIG
        from .report_bot import USER_STATES
        
        config = EVENT_CONFIG.get(event_type, EVENT_CONFIG.get("other", {}))
        icon = config.get("icon", "⚠️")
        label = config.get("label", event_type)
        
        # Set state for waiting text/photo
        USER_STATES[actor_id] = {
            "step": "waiting_description",
            "signalType": event_type
        }
        
        text = (
            f"{icon} *{label}*\n\n"
            "Надішліть опис ситуації.\n"
            "Також можете додати фото 📷\n\n"
            "_Або натисніть 'Пропустити' для відправки без опису_"
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "⏭ Пропустити опис", "callback_data": f"skip_description:{event_type}"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "waiting_description"}
    
    async def _handle_skip_to_photo(self, chat_id: int, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Skip description, ask for photo directly"""
        from .report_bot import USER_STATES
        from .bot_keyboard_builder import EVENT_ICONS
        
        icon = EVENT_ICONS.get(event_type, "📍")
        
        USER_STATES[actor_id] = {
            "step": "waiting_photo",
            "signalType": event_type,
            "description": None,
            "mode": "photo"
        }
        
        await self.send_message(
            chat_id=chat_id,
            text=f"{icon} Надішліть фото:",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "⏭ Надіслати без фото", "callback_data": f"send_without_photo:{event_type}"}],
                    [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                ]
            }
        )
        
        return {"ok": True, "action": "waiting_photo"}
    
    async def _handle_skip_description(self, chat_id: int, actor_id: str, event_type: str) -> Dict[str, Any]:
        """Skip description and go to location/send"""
        from .report_bot import USER_STATES
        
        USER_STATES[actor_id] = {
            "step": "waiting_location_detailed",
            "signalType": event_type,
            "description": None,
            "photoUrl": None
        }
        
        # Check if location exists
        location = await self.location_service.get_location(actor_id)
        if location:
            # Has location - create signal
            return await self._create_detailed_signal(chat_id, actor_id, event_type, None, None)
        else:
            # Need location
            await self.send_message(
                chat_id=chat_id,
                text="📍 Надішліть свою локацію для створення сигналу:",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": True, "action": "waiting_location"}
    
    async def _create_detailed_signal(
        self, 
        chat_id: int, 
        actor_id: str, 
        event_type: str, 
        description: str = None, 
        photo_url: str = None
    ) -> Dict[str, Any]:
        """Create signal with optional description and photo"""
        from .crowd_signal_service import CrowdSignalService, EVENT_CONFIG
        from .report_bot import USER_STATES
        from .trust_score_service import TrustScoreService
        from .admin_moderation_service import AdminModerationService
        
        # Get location
        location = await self.location_service.get_location(actor_id)
        if not location:
            # Save state and request location
            USER_STATES[actor_id] = {
                "step": "waiting_location_detailed",
                "signalType": event_type,
                "description": description,
                "photoUrl": photo_url,
                "mode": "photo"
            }
            await self.send_message(
                chat_id=chat_id,
                text="📍 Надішліть локацію:",
                reply_markup=self.keyboard.location_request()
            )
            return {"ok": True, "action": "waiting_location"}
        
        # Clear state
        USER_STATES.pop(actor_id, None)
        
        # Check if moderation required
        trust_svc = TrustScoreService(self.db)
        mod_check = await trust_svc.requires_moderation(actor_id, has_photo=bool(photo_url))
        
        # Create event
        crowd_service = CrowdSignalService(self.db)
        result = await crowd_service.create_event(
            actor_id=actor_id,
            event_type=event_type,
            lat=location["lat"],
            lng=location["lng"],
            comment=description,
            photo_url=photo_url
        )
        
        if result.get("ok"):
            config = EVENT_CONFIG.get(event_type, EVENT_CONFIG.get("other", {}))
            icon = config.get("icon", "⚠️")
            label = config.get("label", event_type)
            
            # Calculate reward preview based on content
            base_reward = 0.30  # $0.30 базова за сигнал
            photo_bonus = 0.10 if photo_url else 0  # +$0.10 за фото
            total_reward = base_reward + photo_bonus
            
            if mod_check.get("required"):
                # Submit for moderation
                mod_svc = AdminModerationService(self.db)
                await mod_svc.submit_for_moderation(
                    signal_id=result.get("eventId", ""),
                    actor_id=actor_id,
                    signal_type=event_type,
                    text=description,
                    photo_url=photo_url,
                    lat=location["lat"],
                    lng=location["lng"]
                )
                
                text = (
                    f"📩 *Сигнал надіслано на модерацію*\n\n"
                    f"Дякуємо!\n\n"
                    f"🫡 +${total_reward:.2f}"
                )
            else:
                if result.get("action") == "merged":
                    text = (
                        f"✅ *Сигнал підтверджено*\n\n"
                        f"Дякуємо!\n\n"
                        f"🫡 +$0.05"
                    )
                else:
                    text = (
                        f"✅ *Сигнал створено*\n\n"
                        f"Дякуємо!\n\n"
                        f"🫡 +${total_reward:.2f}"
                    )
            
            await self.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=self.keyboard.main_menu(),
                parse_mode="Markdown"
            )
        else:
            await self.send_message(
                chat_id=chat_id,
                text=f"❌ Помилка: {result.get('message', 'Unknown error')}",
                reply_markup=self.keyboard.main_menu()
            )
        
        return result
    
    async def _handle_confirm_event(self, chat_id: int, actor_id: str, event_id: str, confirmed: bool) -> Dict[str, Any]:
        """Handle event confirmation with rewards"""
        from .crowd_signal_service import CrowdSignalService
        from .rewards_service import RewardsService
        
        crowd_service = CrowdSignalService(self.db)
        result = await crowd_service.add_confirmation(event_id, actor_id, confirmed)
        
        if confirmed:
            # Award rewards for confirmation
            rewards_svc = RewardsService(self.db)
            
            # Get signal creator
            signal = await self.db.tg_crowd_signals.find_one({"_id": event_id})
            creator_id = signal.get("actorId") if signal else None
            
            reward_result = await rewards_svc.reward_confirmation(actor_id, event_id, creator_id)
            
            if reward_result.get("ok"):
                reward_stars = reward_result.get("rewardStars", 0)
                strength = reward_result.get("signalStrength", "")
                text = f"✅ *Підтверджено!*\n\n{strength}\n\n💰 +{reward_stars} ⭐ за підтвердження"
            else:
                text = "✅ Дякуємо за підтвердження!"
        else:
            text = "👍 Дякуємо за відгук!"
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=self.keyboard.main_menu(),
            parse_mode="Markdown"
        )
        
        return result
    
    async def _handle_signal_confirmation(
        self, 
        chat_id: int, 
        message_id: int, 
        actor_id: str, 
        signal_id: str, 
        action: str,
        is_batch: bool = False
    ) -> Dict[str, Any]:
        """
        Handle signal confirmation from proximity alert.
        Updates signal confidence, rewards, and user stats.
        """
        import os
        import httpx
        from .crowd_signal_service import CrowdSignalService
        from .report_ingestion import update_user_stats
        from .rewards_service import RewardsService
        
        confirmed = action in ("yes", "confirm")
        
        # Update signal in database
        crowd_service = CrowdSignalService(self.db)
        result = await crowd_service.add_confirmation(signal_id, actor_id, confirmed)
        
        # Update user stats (increase radar score for confirmations)
        reward_text = ""
        if confirmed:
            await update_user_stats(self.db, actor_id, action="confirm")
            
            # Award rewards
            rewards_svc = RewardsService(self.db)
            signal = await self.db.tg_crowd_signals.find_one({"_id": signal_id})
            creator_id = signal.get("actorId") if signal else None
            
            reward_result = await rewards_svc.reward_confirmation(actor_id, signal_id, creator_id)
            
            if reward_result.get("ok"):
                reward_stars = reward_result.get("rewardStars", 0)
                strength = reward_result.get("signalStrength", "")
                reward_text = f"\n{strength}\n💰 +{reward_stars} ⭐"
        
        # Edit original message to show result
        bot_token = os.environ.get("TG_BOT_TOKEN", "")
        if bot_token:
            if confirmed:
                new_text = f"✅ Підтверджено! Дякуємо 🙏{reward_text}"
            else:
                new_text = "👍 Дякуємо за відгук!"
            
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{bot_token}/editMessageText",
                        json={
                            "chat_id": chat_id,
                            "message_id": message_id,
                            "text": new_text
                        },
                        timeout=5.0
                    )
            except Exception as e:
                logger.warning(f"Failed to edit confirmation message: {e}")
        
        return {"ok": True, "action": "confirmed" if confirmed else "rejected", "signal_id": signal_id}
    
    async def _handle_mute(self, chat_id: int, actor_id: str, data: str) -> Dict[str, Any]:
        """Handle mute request"""
        # Parse mute duration
        if "1h" in data:
            hours = 1
        elif "6h" in data:
            hours = 6
        elif "24h" in data:
            hours = 24
        else:
            # Show mute options
            await self.send_message(
                chat_id=chat_id,
                text="🔕 На скільки вимкнути сповіщення?",
                reply_markup=self.keyboard.mute_options()
            )
            return {"ok": True, "action": "show_mute"}
        
        # Set mute (could store in settings)
        # For now just acknowledge
        await self.send_message(
            chat_id=chat_id,
            text=f"🔕 Сповіщення вимкнено на {hours} год",
            reply_markup=self.keyboard.main_menu()
        )
        
        return {"ok": True, "action": "muted", "hours": hours}
    
    # ==================== Alert Sending ====================
    
    async def send_proximity_alert(
        self,
        chat_id: int,
        events: list,
        user_lat: float,
        user_lng: float,
        radius: int
    ) -> Dict[str, Any]:
        """Send proximity alert to user"""
        actor_id = f"tg_{chat_id}"
        
        if not events:
            return {"ok": False, "error": "no_events"}
        
        # Check cooldown
        first_event = events[0]
        can_send = await self.alert_service.can_send_alert(
            actor_id=actor_id,
            event_id=str(first_event.get("id", first_event.get("_id", ""))),
            event_type=first_event.get("eventType", "unknown")
        )
        
        if not can_send:
            return {"ok": False, "error": "cooldown"}
        
        # Format message
        text = self.alert_service.format_proximity_alert(events, user_lat, user_lng, radius)
        
        # Send
        await self.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown"
        )
        
        # Log
        await self.alert_service.log_alert(
            actor_id=actor_id,
            event_id=str(first_event.get("id", first_event.get("_id", ""))),
            event_type=first_event.get("eventType", "unknown"),
            alert_type="PROXIMITY"
        )
        
        return {"ok": True, "sent": True}

    # ==================== Admin Moderation Handlers ====================
    
    async def _handle_admin_approve(self, chat_id: int, callback_query: Dict, signal_id: str) -> Dict[str, Any]:
        """Handle admin approval of a signal"""
        from .admin_moderation_service import AdminModerationService
        
        admin_id = callback_query.get("from", {}).get("id")
        mod_svc = AdminModerationService(self.db)
        
        if not mod_svc.is_admin(admin_id):
            return {"ok": False, "error": "Not admin"}
        
        result = await mod_svc.approve_signal(signal_id, admin_id)
        
        if result.get("ok"):
            # Edit the message to show approval
            message_id = callback_query["message"]["message_id"]
            await self._edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="✅ *Сигнал підтверджено*\n\nОпубліковано.",
                parse_mode="Markdown"
            )
        
        return result
    
    async def _handle_admin_reject(self, chat_id: int, callback_query: Dict, signal_id: str) -> Dict[str, Any]:
        """Handle admin rejection of a signal"""
        from .admin_moderation_service import AdminModerationService
        
        admin_id = callback_query.get("from", {}).get("id")
        mod_svc = AdminModerationService(self.db)
        
        if not mod_svc.is_admin(admin_id):
            return {"ok": False, "error": "Not admin"}
        
        result = await mod_svc.reject_signal(signal_id, admin_id)
        
        if result.get("ok"):
            message_id = callback_query["message"]["message_id"]
            await self._edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text="❌ *Сигнал відхилено*",
                parse_mode="Markdown"
            )
        
        return result
    
    async def _handle_admin_ban(self, chat_id: int, callback_query: Dict, signal_id: str) -> Dict[str, Any]:
        """Handle admin ban of a user"""
        from .admin_moderation_service import AdminModerationService
        
        admin_id = callback_query.get("from", {}).get("id")
        mod_svc = AdminModerationService(self.db)
        
        if not mod_svc.is_admin(admin_id):
            return {"ok": False, "error": "Not admin"}
        
        # Get signal to find user
        queue_item = await self.db.geo_moderation_queue.find_one({"signalId": signal_id})
        if not queue_item:
            return {"ok": False, "error": "Signal not found"}
        
        user_actor_id = queue_item.get("actorId")
        
        # Show ban duration options
        await self.send_message(
            chat_id=chat_id,
            text=f"🚫 *Заблокувати @{queue_item.get('username', 'user')}*\n\nОберіть тривалість:",
            reply_markup={
                "inline_keyboard": [
                    [{"text": "⚠️ Попередження", "callback_data": f"admin_ban_do:{user_actor_id}:warning"}],
                    [{"text": "24 години", "callback_data": f"admin_ban_do:{user_actor_id}:short"}],
                    [{"text": "7 днів", "callback_data": f"admin_ban_do:{user_actor_id}:medium"}],
                    [{"text": "30 днів", "callback_data": f"admin_ban_do:{user_actor_id}:long"}],
                    [{"text": "❌ Скасувати", "callback_data": "cancel"}]
                ]
            },
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "show_ban_options"}
    
    async def _edit_message_text(self, chat_id: int, message_id: int, text: str, parse_mode: str = None):
        """Edit existing message text"""
        import httpx
        import os
        
        bot_token = os.environ.get("TG_BOT_TOKEN")
        if not bot_token:
            return
        
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/editMessageText",
                    json={
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "text": text,
                        "parse_mode": parse_mode
                    },
                    timeout=10.0
                )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
    
    # ==================== Admin Panel ====================
    
    async def show_admin_panel(self, chat_id: int, admin_id: int) -> Dict[str, Any]:
        """Show admin panel for moderators"""
        from .admin_moderation_service import AdminModerationService
        
        mod_svc = AdminModerationService(self.db)
        
        if not mod_svc.is_admin(admin_id):
            return {"ok": False, "error": "Not admin"}
        
        pending_count = await mod_svc.get_pending_count()
        
        text = (
            "🛠 *Admin Panel*\n\n"
            f"📩 На модерації: {pending_count}\n\n"
            "Натисніть кнопку для перегляду черги:"
        )
        
        await self.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup={
                "inline_keyboard": [
                    [{"text": f"📩 Черга ({pending_count})", "callback_data": "admin_queue"}],
                    [{"text": "📊 Статистика", "callback_data": "admin_stats"}],
                    [{"text": "↩️ Назад", "callback_data": "menu_back"}]
                ]
            },
            parse_mode="Markdown"
        )
        
        return {"ok": True, "action": "admin_panel"}

