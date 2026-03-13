"""
Telegram Channel Publisher Service
Publishes alerts/signals to Telegram channel with beautiful formatting
"""
import os
import httpx
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Signal type configurations with emoji and descriptions
SIGNAL_CONFIG = {
    "danger": {
        "emoji": "🚨",
        "title": "НЕБЕЗПЕКА",
        "color": "🔴",
        "priority": "high",
        "call_to_action": "Будьте обережні!"
    },
    "police": {
        "emoji": "🚔",
        "title": "ПОЛІЦІЯ",
        "color": "🔵",
        "priority": "medium",
        "call_to_action": "Дотримуйтесь ПДР"
    },
    "incident": {
        "emoji": "⚠️",
        "title": "ІНЦИДЕНТ",
        "color": "🟡",
        "priority": "medium",
        "call_to_action": "Оминайте цю ділянку"
    },
    "weather": {
        "emoji": "🌧️",
        "title": "ПОГОДА",
        "color": "🟣",
        "priority": "low",
        "call_to_action": "Візьміть парасольку"
    },
    "virus": {
        "emoji": "☣️",
        "title": "БІОЗАГРОЗА",
        "color": "🟢",
        "priority": "high",
        "call_to_action": "Тримайте дистанцію"
    },
    "trash": {
        "emoji": "🗑️",
        "title": "СМІТТЯ",
        "color": "🟤",
        "priority": "low",
        "call_to_action": "Повідомте комунальні служби"
    },
    "fire": {
        "emoji": "🔥",
        "title": "ПОЖЕЖА",
        "color": "🔴",
        "priority": "critical",
        "call_to_action": "Викличте 101!"
    },
    "accident": {
        "emoji": "💥",
        "title": "ДТП",
        "color": "🟠",
        "priority": "high",
        "call_to_action": "Оминайте місце аварії"
    },
    "flood": {
        "emoji": "🌊",
        "title": "ПІДТОПЛЕННЯ",
        "color": "🔵",
        "priority": "medium",
        "call_to_action": "Шукайте об'їзний шлях"
    },
    "road_works": {
        "emoji": "🚧",
        "title": "ДОРОЖНІ РОБОТИ",
        "color": "🟡",
        "priority": "low",
        "call_to_action": "Очікуйте затримки"
    }
}

# Default config for unknown types
DEFAULT_CONFIG = {
    "emoji": "📍",
    "title": "СИГНАЛ",
    "color": "⚪",
    "priority": "medium",
    "call_to_action": "Будьте уважні"
}

class ChannelPublisher:
    """Service for publishing alerts to Telegram channel"""
    
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id  # @ARKHOR or chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
    
    def _get_signal_config(self, signal_type: str) -> Dict[str, Any]:
        """Get configuration for signal type"""
        return SIGNAL_CONFIG.get(signal_type, DEFAULT_CONFIG)
    
    def _get_priority_indicator(self, priority: str) -> str:
        """Get visual priority indicator"""
        indicators = {
            "critical": "🔴🔴🔴",
            "high": "🔴🔴",
            "medium": "🟡",
            "low": "🟢"
        }
        return indicators.get(priority, "⚪")
    
    def _format_time(self, dt: Optional[datetime] = None) -> str:
        """Format time in Ukrainian locale"""
        if dt is None:
            dt = datetime.now(timezone.utc)
        
        # Convert to Kyiv time (UTC+2/+3)
        kyiv_offset = 2  # Winter time, adjust for summer
        kyiv_time = dt.replace(tzinfo=None)
        
        return kyiv_time.strftime("%H:%M")
    
    def _format_location_link(self, lat: float, lng: float) -> str:
        """Create Google Maps link"""
        return f"https://maps.google.com/?q={lat},{lng}"
    
    def _get_area_name(self, lat: float, lng: float) -> str:
        """Get approximate area name based on coordinates (Kyiv districts)"""
        # Simplified Kyiv district detection
        if lat > 50.48:
            if lng < 30.45:
                return "Оболонь"
            elif lng < 30.55:
                return "Поділ"
            else:
                return "Дніпровський р-н"
        elif lat > 50.42:
            if lng < 30.45:
                return "Святошино"
            elif lng < 30.55:
                return "Центр"
            else:
                return "Лівий берег"
        else:
            if lng < 30.45:
                return "Теремки"
            elif lng < 30.55:
                return "Печерськ"
            else:
                return "Харківський р-н"
    
    def format_alert_post(self, signal: Dict[str, Any]) -> str:
        """
        Format signal into beautiful Telegram post
        
        Returns formatted message with HTML markup
        """
        signal_type = signal.get("type", "incident")
        config = self._get_signal_config(signal_type)
        
        lat = signal.get("lat", 0)
        lng = signal.get("lng", 0)
        description = signal.get("description", "")
        created_at = signal.get("createdAt")
        confirmations = signal.get("confirmations", 0)
        
        # Build the post
        emoji = config["emoji"]
        title = config["title"]
        priority = self._get_priority_indicator(config["priority"])
        call_to_action = config["call_to_action"]
        
        area = self._get_area_name(lat, lng)
        time_str = self._format_time(created_at)
        map_link = self._format_location_link(lat, lng)
        
        # Format message with HTML
        lines = [
            f"{emoji} <b>{title}</b> {priority}",
            "",
            f"📍 <b>Локація:</b> {area}",
            f"🕐 <b>Час:</b> {time_str}",
        ]
        
        # Add description if provided
        if description and description.strip():
            lines.append(f"")
            lines.append(f"💬 {description}")
        
        # Add confirmations if any
        if confirmations > 0:
            lines.append(f"")
            lines.append(f"✅ Підтверджено: {confirmations}")
        
        # Add separator and call to action
        lines.extend([
            "",
            f"━━━━━━━━━━━━━━━",
            f"⚡ {call_to_action}",
            "",
            f"🗺️ <a href=\"{map_link}\">Переглянути на карті</a>",
            "",
            f"#radar #{signal_type} #{area.replace(' ', '_').replace('-', '_')}"
        ])
        
        return "\n".join(lines)
    
    def format_summary_post(self, signals: list, period: str = "година") -> str:
        """
        Format multiple signals into summary post
        """
        if not signals:
            return None
        
        # Count by type
        type_counts = {}
        for s in signals:
            t = s.get("type", "incident")
            type_counts[t] = type_counts.get(t, 0) + 1
        
        lines = [
            f"📊 <b>ЗВЕДЕННЯ ЗА {period.upper()}</b>",
            "",
            f"Всього сигналів: <b>{len(signals)}</b>",
            ""
        ]
        
        for signal_type, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            config = self._get_signal_config(signal_type)
            lines.append(f"{config['emoji']} {config['title']}: {count}")
        
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━",
            "📱 Слідкуйте за оновленнями в боті",
            "#radar #зведення"
        ])
        
        return "\n".join(lines)
    
    async def publish_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Publish single signal to channel
        
        Returns: {"ok": bool, "message_id": int} or {"ok": False, "error": str}
        """
        try:
            message = self.format_alert_post(signal)
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/sendMessage",
                    json={
                        "chat_id": self.channel_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False
                    },
                    timeout=10.0
                )
                
                data = response.json()
                
                if data.get("ok"):
                    message_id = data.get("result", {}).get("message_id")
                    logger.info(f"Published signal to channel: {message_id}")
                    return {"ok": True, "message_id": message_id}
                else:
                    error = data.get("description", "Unknown error")
                    logger.error(f"Failed to publish: {error}")
                    return {"ok": False, "error": error}
                    
        except Exception as e:
            logger.error(f"Channel publish error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def publish_summary(self, signals: list, period: str = "година") -> Dict[str, Any]:
        """Publish summary post to channel"""
        try:
            message = self.format_summary_post(signals, period)
            if not message:
                return {"ok": False, "error": "No signals to summarize"}
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base}/sendMessage",
                    json={
                        "chat_id": self.channel_id,
                        "text": message,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True
                    },
                    timeout=10.0
                )
                
                data = response.json()
                
                if data.get("ok"):
                    return {"ok": True, "message_id": data["result"]["message_id"]}
                else:
                    return {"ok": False, "error": data.get("description")}
                    
        except Exception as e:
            logger.error(f"Summary publish error: {e}")
            return {"ok": False, "error": str(e)}


def get_channel_publisher() -> Optional[ChannelPublisher]:
    """Factory function to create ChannelPublisher"""
    bot_token = os.environ.get("BOT_TOKEN")
    channel_id = os.environ.get("CHANNEL_ID", "@ARKHOR")
    
    if not bot_token:
        logger.warning("BOT_TOKEN not set, channel publishing disabled")
        return None
    
    return ChannelPublisher(bot_token, channel_id)
