"""
Telegram Alert Notifier Service
Sends proximity alerts via Telegram Bot API with confirmation buttons
"""
import os
import logging
import httpx
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Get bot token from environment
BOT_TOKEN = os.environ.get("GEO_BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")


async def send_telegram_alert(
    chat_id: int,
    text: str,
    parse_mode: str = "HTML",
    bot_token: str = None,
    reply_markup: Dict[str, Any] = None
) -> Dict:
    """
    Send alert message via Telegram Bot API.
    Supports inline keyboard for confirmations.
    """
    token = bot_token or BOT_TOKEN
    
    if not token:
        logger.warning("No bot token configured for Telegram alerts")
        return {"ok": False, "error": "NO_BOT_TOKEN"}
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                timeout=10.0
            )
            
            data = response.json()
            
            if data.get("ok"):
                logger.info(f"Alert sent to chat {chat_id}")
                return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
            else:
                logger.error(f"Telegram API error: {data}")
                return {"ok": False, "error": data.get("description")}
                
    except Exception as e:
        logger.error(f"Send alert error: {e}")
        return {"ok": False, "error": str(e)}


def format_proximity_alert(
    event_type: str,
    title: str,
    distance: int,
    minutes_ago: int,
    confidence: float = 0.5,
    base_url: str = None
) -> str:
    """
    Format proximity alert - NEW with question.
    """
    # Event type emoji only
    emoji_map = {
        "virus": "🦠",
        "trash": "🗑",
        "rain": "🌧",
        "block": "🚧",
        "police": "🚔"
    }
    type_emoji = emoji_map.get(event_type, "🚔")
    
    # Time formatting
    if minutes_ago < 60:
        time_str = f"{minutes_ago} хв"
    elif minutes_ago < 1440:
        time_str = f"{minutes_ago // 60} год"
    else:
        time_str = f"{minutes_ago // 1440} дн"
    
    # Confidence emoji
    if confidence >= 0.8:
        conf_emoji = "🟢"
    elif confidence >= 0.5:
        conf_emoji = "🟡"
    else:
        conf_emoji = "⚪"
    
    text = f"Поруч сигнал {type_emoji}\n\n📍 {distance}м • {time_str} {conf_emoji}\n\nПідтвердити?"
    
    return text.strip()


def format_multiple_events_alert(
    events: list,
    radius: int,
    base_url: str = None
) -> str:
    """
    Format alert for multiple nearby events - NEW with question.
    """
    count = len(events)
    
    # Count by type
    emoji_map = {"virus": "🦠", "trash": "🗑", "rain": "🌧", "block": "🚧", "police": "🚔"}
    type_counts = {}
    for e in events:
        et = e.get("eventType", "police")
        type_counts[et] = type_counts.get(et, 0) + 1
    
    # Build summary
    summary_parts = [f"{emoji_map.get(t, '🚔')} {c}" for t, c in type_counts.items()]
    
    text = f"Поруч {count} сигналів\n\n{' '.join(summary_parts)}\n📍 в радіусі {radius}м\n\nПідтвердити?"
    
    return text.strip()


def get_confirmation_keyboard(event_id: str) -> Dict:
    """
    Generate inline keyboard for signal confirmation.
    """
    return {
        "inline_keyboard": [
            [
                {"text": "✔ Так", "callback_data": f"confirm:{event_id}:yes"},
                {"text": "✖ Ні", "callback_data": f"confirm:{event_id}:no"}
            ]
        ]
    }


def get_multi_confirmation_keyboard(event_ids: list) -> Dict:
    """
    Generate inline keyboard for multiple signals confirmation.
    First event_id is used as reference.
    """
    first_id = event_ids[0] if event_ids else "batch"
    return {
        "inline_keyboard": [
            [
                {"text": "✔ Так, бачу", "callback_data": f"confirm_batch:{first_id}:yes"},
                {"text": "✖ Ні", "callback_data": f"confirm_batch:{first_id}:no"}
            ]
        ]
    }


async def send_test_alert(chat_id: int, bot_token: str = None) -> Dict:
    """
    Send test alert to verify bot connection.
    """
    text = """
✅ <b>Geo Radar Bot підключено</b>

Бот налаштовано правильно.
Ви будете отримувати сповіщення про події поблизу:

🦠 Вірус
🗑️ Сміття

Щоб налаштувати радіус — використовуйте веб-інтерфейс.
"""
    
    return await send_telegram_alert(chat_id, text.strip(), bot_token=bot_token)
