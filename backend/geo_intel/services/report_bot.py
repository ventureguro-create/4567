"""
Geo Radar Bot - User Report Commands
Fast signal reporting via Telegram Bot (Waze-style)
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
BOT_USERNAME = os.environ.get('TG_BOT_USERNAME', 'GeoRadarBot')

# Event types - emoji only, no text
REPORT_TYPES = [
    {"type": "virus", "emoji": "🦠"},
    {"type": "trash", "emoji": "🗑"},
    {"type": "rain", "emoji": "🌧"},
    {"type": "block", "emoji": "🚧"},
    {"type": "police", "emoji": "🚔"}
]

# User states for conversation flow
USER_STATES = {}  # actor_id -> state dict


def get_report_types_keyboard() -> Dict:
    """Inline keyboard for event type selection - emoji only in one row"""
    row = []
    for rt in REPORT_TYPES:
        row.append({
            "text": rt['emoji'],
            "callback_data": f"report_type:{rt['type']}"
        })
    
    return {"inline_keyboard": [row, [{"text": "❌ Скасувати", "callback_data": "cancel"}]]}


def get_location_keyboard(has_saved: bool = False) -> Dict:
    """Keyboard for location request with clear instructions"""
    return {
        "keyboard": [
            [{"text": "📍 Надіслати моє місце", "request_location": True}],
            ["❌ Скасувати"]
        ],
        "resize_keyboard": True,
        "one_time_keyboard": True
    }


def get_photo_keyboard() -> Dict:
    """Keyboard for photo option"""
    return {
        "inline_keyboard": [
            [
                {"text": "📷 Додати фото", "callback_data": "report_photo:add"},
                {"text": "➡️ Без фото", "callback_data": "report_photo:skip"}
            ]
        ]
    }


def get_confirmation_keyboard(report_id: str) -> Dict:
    """Keyboard for confirming/rejecting a signal"""
    return {
        "inline_keyboard": [
            [
                {"text": "✔️ Підтверджую", "callback_data": f"confirm:{report_id}:confirm"},
                {"text": "❌ Немає", "callback_data": f"confirm:{report_id}:reject"}
            ],
            [
                {"text": "🚫 Хибний сигнал", "callback_data": f"confirm:{report_id}:false"}
            ]
        ]
    }


def get_main_keyboard() -> Dict:
    """Main reply keyboard - Clean 3-button UI"""
    return {
        "keyboard": [
            [{"text": "➕ Повідомити"}],
            [{"text": "📡 Радар"}, {"text": "👤 Профіль"}]
        ],
        "resize_keyboard": True
    }


async def send_telegram_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> Dict:
    """Send message via Telegram Bot API"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not set"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": parse_mode
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload)
            return response.json()
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return {"ok": False, "error": str(e)}


async def edit_telegram_message(chat_id: int, message_id: int, text: str, reply_markup: dict = None) -> Dict:
    """Edit existing message"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not set"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text[:4096],
        "parse_mode": "HTML"
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload)
            return response.json()
        except Exception as e:
            logger.error(f"Telegram edit error: {e}")
            return {"ok": False, "error": str(e)}


async def handle_report_command(db, chat_id: int, actor_id: str, username: str = None) -> Dict:
    """Handle /report or "Повідомити" command - start report flow with mode selection first"""
    from geo_intel.services.report_ingestion import check_spam_limits, get_or_create_user_profile
    
    # Check if user has location saved
    user_location = await db.geo_bot_locations.find_one({"actorId": actor_id})
    has_location = user_location and user_location.get("lat") and user_location.get("lng")
    
    # Check spam limits
    spam_check = await check_spam_limits(db, actor_id)
    if not spam_check["allowed"]:
        if spam_check.get("reason") == "cooldown":
            remaining = spam_check['remaining_seconds']
            text = f"⏳ Зачекайте {remaining} сек. перед наступним сигналом"
        elif spam_check.get("reason") == "hourly_limit":
            count = spam_check['count']
            text = (
                f"⏳ *Досягнуто ліміт: {count}/10 сигналів за годину*\n\n"
                f"Ви надіслали максимальну кількість сигналів.\n"
                f"Спробуйте пізніше - ліміт оновиться через годину.\n\n"
                f"💡 _Це обмеження захищає систему від спаму_"
            )
        else:
            count = spam_check['count']
            text = (
                f"⏳ *Досягнуто денний ліміт: {count}/50 сигналів*\n\n"
                f"Ви надіслали максимальну кількість сигналів за сьогодні.\n"
                f"Ліміт оновиться завтра.\n\n"
                f"💡 _Дякуємо за активність!_"
            )
        
        await send_telegram_message(chat_id, text, get_main_keyboard(), parse_mode="Markdown")
        return {"ok": False, "reason": "spam_limit"}
    
    # Ensure user profile exists
    await get_or_create_user_profile(db, actor_id, username)
    
    # Set user state - first choose mode (instant or with photo)
    USER_STATES[actor_id] = {
        "step": "choose_mode",
        "chat_id": chat_id,
        "has_location": has_location,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Show mode selection: instant or with photo (horizontal buttons)
    text = "Оберіть спосіб:"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "⚡ Миттєво", "callback_data": "mode_instant"},
                {"text": "📷 З фото", "callback_data": "mode_photo"}
            ],
            [{"text": "❌ Скасувати", "callback_data": "cancel"}]
        ]
    }
    await send_telegram_message(chat_id, text, keyboard)
    
    return {"ok": True, "step": "choose_mode"}


async def handle_mode_callback(db, chat_id: int, message_id: int, actor_id: str, mode: str) -> Dict:
    """Handle mode selection callback (instant or photo)"""
    
    state = USER_STATES.get(actor_id)
    if not state or state.get("step") != "choose_mode":
        return {"ok": False, "error": "INVALID_STATE"}
    
    # Update state with selected mode
    USER_STATES[actor_id] = {
        **state,
        "step": "select_type",
        "mode": mode  # "instant" or "photo"
    }
    
    # Show type selection - all icons in one row
    if mode == "instant":
        text = "⚡ Оберіть тип:"
    else:
        text = "📷 Оберіть тип:"
    
    # Icons in one horizontal row
    type_buttons = []
    for rt in REPORT_TYPES:
        type_buttons.append({
            "text": rt['emoji'],
            "callback_data": f"report_type:{rt['type']}"
        })
    
    keyboard = {
        "inline_keyboard": [
            type_buttons,  # All types in one row
            [{"text": "❌ Скасувати", "callback_data": "cancel"}]
        ]
    }
    
    await edit_telegram_message(chat_id, message_id, text, keyboard)
    
    return {"ok": True, "step": "select_type", "mode": mode}


async def handle_report_type_callback(db, chat_id: int, message_id: int, actor_id: str, event_type: str) -> Dict:
    """Handle event type selection callback - process based on mode"""
    from geo_intel.services.report_ingestion import create_user_report, update_radar_score
    
    state = USER_STATES.get(actor_id)
    if not state or state.get("step") != "select_type":
        return {"ok": False, "error": "INVALID_STATE"}
    
    # Find type config
    type_config = next((t for t in REPORT_TYPES if t["type"] == event_type), REPORT_TYPES[-1])
    mode = state.get("mode", "instant")
    
    if mode == "instant":
        # Instant mode - send signal immediately if has location
        # Миттєво = точна геолокація = $0.40 (як текст + фото)
        user_location = await db.geo_bot_locations.find_one({"actorId": actor_id})
        
        if user_location and user_location.get("lat") and user_location.get("lng"):
            # Create report immediately
            result = await create_user_report(
                db,
                actor_id=actor_id,
                event_type=event_type,
                lat=user_location["lat"],
                lng=user_location["lng"],
                username=None
            )
            
            # Clear state
            USER_STATES.pop(actor_id, None)
            
            instant_reward = 0.40  # $0.40 за точну геолокацію
            
            if result.get("ok"):
                await update_radar_score(db, actor_id, 8, "instant_report")
                text = (
                    f"✅ *Сигнал створено*\n\n"
                    f"Дякуємо!\n\n"
                    f"🫡 +${instant_reward:.2f}"
                )
                await edit_telegram_message(chat_id, message_id, text)
            else:
                await edit_telegram_message(chat_id, message_id, "❌ Помилка")
            
            return result
        else:
            # No location - request it
            USER_STATES[actor_id] = {
                "step": "waiting_location_instant",
                "signalType": event_type,
                "event_emoji": type_config["emoji"],
                "mode": "instant"
            }
            
            text = "📍 Надішліть локацію"
            await edit_telegram_message(chat_id, message_id, text)
            await send_telegram_message(chat_id, "📍", get_location_keyboard(False))
            
            return {"ok": True, "step": "waiting_location_instant"}
    
    else:
        # Photo mode - STEP 1: wait for text description first
        USER_STATES[actor_id] = {
            "step": "waiting_description_first",
            "signalType": event_type,
            "event_emoji": type_config["emoji"],
            "mode": "photo"
        }
        
        text = f"{type_config['emoji']} Крок 1: Напишіть опис або адресу:"
        keyboard = {
            "inline_keyboard": [
                [{"text": "⏭ Пропустити опис", "callback_data": f"skip_desc:{event_type}"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
        
        await edit_telegram_message(chat_id, message_id, text, keyboard)
        
        return {"ok": True, "step": "waiting_description_first"}


async def handle_location_message(db, chat_id: int, actor_id: str, lat: float, lng: float, username: str = None) -> Dict:
    """Handle location message from user"""
    from geo_intel.services.report_ingestion import create_user_report, update_radar_score
    
    state = USER_STATES.get(actor_id)
    if not state or state.get("step") != "send_location":
        # Direct quick report without flow
        return {"ok": False, "error": "NO_ACTIVE_REPORT"}
    
    event_type = state.get("event_type", "police")
    
    # Create report immediately after receiving location
    result = await create_user_report(
        db,
        actor_id=actor_id,
        event_type=event_type,
        lat=lat,
        lng=lng,
        username=username
    )
    
    # Clear state
    USER_STATES.pop(actor_id, None)
    
    if result.get("ok"):
        # Award points
        await update_radar_score(db, actor_id, 5, "new_report")
        
        # Save location for future
        await db.geo_bot_locations.update_one(
            {"actorId": actor_id},
            {"$set": {"lat": lat, "lng": lng, "updatedAt": datetime.now(timezone.utc)}},
            upsert=True
        )
        
        # Success message with reward
        text = (
            "✅ *Сигнал надіслано*\n\n"
            "🎉 Дякуємо за повідомлення!\n"
            "💰 +$0.30"
        )
        await send_telegram_message(chat_id, text, get_main_keyboard())
    else:
        await send_telegram_message(chat_id, "❌ Помилка", get_main_keyboard())
    
    return result


async def handle_photo_callback(db, chat_id: int, message_id: int, actor_id: str, action: str, username: str = None) -> Dict:
    """Handle photo option callback"""
    from geo_intel.services.report_ingestion import create_user_report, update_radar_score
    
    state = USER_STATES.get(actor_id)
    if not state or state.get("step") != "photo_option":
        return {"ok": False, "error": "INVALID_STATE"}
    
    if action == "add":
        # Wait for photo
        USER_STATES[actor_id] = {**state, "step": "waiting_photo"}
        await edit_telegram_message(chat_id, message_id, "📷")
        return {"ok": True, "step": "waiting_photo"}
    
    # Skip photo - submit report
    result = await create_user_report(
        db,
        actor_id=actor_id,
        event_type=state["event_type"],
        lat=state["lat"],
        lng=state["lng"],
        username=username,
        address_text=state.get("address_text")
    )
    
    # Clear state
    USER_STATES.pop(actor_id, None)
    
    if result.get("ok"):
        # Award points
        xp_earned = 5
        await update_radar_score(db, actor_id, xp_earned, "new_report")
        
        # Get updated user stats
        from geo_intel.services.report_ingestion import get_user_stats
        user_stats = await get_user_stats(db, actor_id)
        total_xp = user_stats.get("radarScore", 0) if user_stats.get("ok") else xp_earned
        
        # Send confirmation - clean with XP
        emoji = state['event_emoji']
        
        if result.get("isConfirmation"):
            text = f"✅ Дякуємо!\n\n+{xp_earned} XP\n🏆 {total_xp}"
        else:
            text = f"✅ {emoji}\n\n+{xp_earned} XP\n🏆 {total_xp}"
        
        await edit_telegram_message(chat_id, message_id, text)
        await send_telegram_message(chat_id, "👍", get_main_keyboard())
    else:
        await edit_telegram_message(chat_id, message_id, "❌")
    
    return result


async def handle_photo_message(db, chat_id: int, actor_id: str, photo_url: str, username: str = None) -> Dict:
    """Handle photo message from user"""
    from geo_intel.services.report_ingestion import create_user_report, update_radar_score
    
    state = USER_STATES.get(actor_id)
    if not state or state.get("step") != "waiting_photo":
        return {"ok": False, "error": "INVALID_STATE"}
    
    # Submit report with photo
    result = await create_user_report(
        db,
        actor_id=actor_id,
        event_type=state["event_type"],
        lat=state["lat"],
        lng=state["lng"],
        username=username,
        photo_url=photo_url,
        address_text=state.get("address_text")
    )
    
    # Clear state
    USER_STATES.pop(actor_id, None)
    
    if result.get("ok"):
        # Award more points for photo
        await update_radar_score(db, actor_id, 8, "report_with_photo")
        
        text = (
            f"✅ <b>Сигнал з фото відправлено</b>\n\n"
            f"{state['event_emoji']} {state['event_label']}\n"
            f"📍 {state.get('address_text', '')}\n"
            f"📷 Фото додано\n"
            f"🕒 щойно\n\n"
            f"Рівень довіри: {'🟢' if result['truthScore'] >= 0.7 else '🟡'} +15%\n"
            f"Очікуємо підтвердження\n\n"
            f"<i>+8 Radar Score</i>"
        )
        
        await send_telegram_message(chat_id, text, get_main_keyboard())
    else:
        await send_telegram_message(chat_id, f"❌ Помилка: {result.get('error', 'unknown')}")
    
    return result


async def handle_confirmation_callback(db, chat_id: int, message_id: int, actor_id: str, report_id: str, action: str) -> Dict:
    """Handle confirmation callback from nearby user"""
    from geo_intel.services.report_ingestion import process_confirmation, update_radar_score
    
    result = await process_confirmation(db, report_id, actor_id, action)
    
    if result.get("ok"):
        if action == "confirm":
            await update_radar_score(db, actor_id, 2, "confirmation_given")
            emoji = "✅"
            text = "Дякуємо за підтвердження!"
        elif action == "reject":
            emoji = "ℹ️"
            text = "Дякуємо за відгук"
        else:  # false
            emoji = "🚫"
            text = "Сигнал позначено як хибний"
        
        await edit_telegram_message(
            chat_id, message_id,
            f"{emoji} {text}\n\nРівень довіри сигналу: {result['newTruthScore']:.0%}"
        )
    else:
        error = result.get("error", "unknown")
        if error == "ALREADY_VOTED":
            await edit_telegram_message(chat_id, message_id, "ℹ️ Ви вже голосували за цей сигнал")
        elif error == "CANNOT_CONFIRM_OWN":
            await edit_telegram_message(chat_id, message_id, "ℹ️ Не можна підтверджувати власний сигнал")
        else:
            await edit_telegram_message(chat_id, message_id, f"❌ Помилка: {error}")
    
    return result


async def handle_status_command(db, chat_id: int, actor_id: str) -> Dict:
    """Handle /status command - show user stats"""
    from geo_intel.services.report_ingestion import get_user_stats
    
    stats = await get_user_stats(db, actor_id)
    
    if not stats.get("ok"):
        text = "📊 <b>Ваша статистика</b>\n\nВи ще не відправляли сигнали"
    else:
        text = (
            f"📊 <b>Ваша статистика</b>\n\n"
            f"🏆 Radar Score: <b>{stats['radarScore']}</b>\n"
            f"⭐ Рівень: {stats['level']}\n"
            f"🎯 Довіра: {stats['trustScore']:.0%}\n\n"
            f"📝 Сигналів: {stats['reportsTotal']}\n"
            f"✅ Підтверджено: {stats['reportsConfirmed']}\n"
            f"👍 Підтверджень дано: {stats['confirmationsGiven']}"
        )
    
    await send_telegram_message(chat_id, text, get_main_keyboard())
    return stats


async def handle_leaderboard_command(db, chat_id: int) -> Dict:
    """Handle /leaderboard command"""
    from geo_intel.services.report_ingestion import get_leaderboard
    
    leaders = await get_leaderboard(db, 10)
    
    if not leaders:
        text = "🏆 <b>Топ репортерів</b>\n\nПоки що немає даних"
    else:
        text = "🏆 <b>Топ репортерів</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, leader in enumerate(leaders):
            medal = medals[i] if i < 3 else f"{i+1}."
            name = leader.get("username") or leader.get("actorId", "Анонім")[:8]
            text += f"{medal} {name} — {leader['radarScore']} pts\n"
    
    await send_telegram_message(chat_id, text, get_main_keyboard())
    return {"ok": True, "leaders": leaders}


async def send_nearby_alert(db, chat_id: int, report: Dict) -> Dict:
    """Send alert to user about nearby signal with confirmation buttons"""
    distance = report.get("distance_meters", 0)
    minutes_ago = report.get("minutes_ago", 0)
    
    text = (
        f"⚠️ <b>Новий сигнал поруч</b>\n\n"
        f"{report.get('eventEmoji', '📍')} {report.get('eventLabel', 'Сигнал')}\n"
        f"📍 {report.get('addressText', 'Невідомо')}\n"
        f"📏 {distance} м від вас\n"
        f"🕒 {minutes_ago} хв тому\n\n"
        f"Рівень: {'🟢 Високий' if report.get('truthScore', 0) >= 0.7 else '🟡 Середній' if report.get('truthScore', 0) >= 0.5 else '⚪ Низький'}\n"
        f"Джерело: користувач\n\n"
        f"<b>Підтверджуєте?</b>"
    )
    
    keyboard = get_confirmation_keyboard(report.get("reportId"))
    await send_telegram_message(chat_id, text, keyboard)
    
    return {"ok": True}


async def handle_quick_report(db, chat_id: int, actor_id: str, lat: float, lng: float, username: str = None) -> Dict:
    """Handle quick 1-tap report using last used type"""
    from geo_intel.services.report_ingestion import create_user_report, update_radar_score
    
    # Get last used type from user profile
    profile = await db.geo_user_profiles.find_one({"actorId": actor_id})
    last_type = profile.get("lastEventType", "other") if profile else "other"
    
    type_config = next((t for t in REPORT_TYPES if t["type"] == last_type), REPORT_TYPES[-1])
    
    # Create report immediately
    result = await create_user_report(
        db,
        actor_id=actor_id,
        event_type=last_type,
        lat=lat,
        lng=lng,
        username=username
    )
    
    if result.get("ok"):
        await update_radar_score(db, actor_id, 5, "quick_report")
        
        text = (
            f"⚡ <b>Швидкий сигнал</b>\n\n"
            f"{type_config['emoji']} {type_config['label']}\n"
            f"📍 {lat:.4f}, {lng:.4f}\n"
            f"✅ Відправлено!\n\n"
            f"<i>+5 Radar Score</i>"
        )
        await send_telegram_message(chat_id, text, get_main_keyboard())
    
    return result
