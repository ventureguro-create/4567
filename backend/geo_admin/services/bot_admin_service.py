"""
Geo Admin - Bot Admin Service
Bot management and control
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("GEO_BOT_TOKEN") or os.environ.get("TG_BOT_TOKEN")


async def get_bot_status(db) -> Dict[str, Any]:
    """Get comprehensive bot status"""
    try:
        if not BOT_TOKEN:
            return {"ok": False, "error": "Bot token not configured"}
        
        async with httpx.AsyncClient(timeout=10) as client:
            # Get bot info
            resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
            bot_info = resp.json()
            
            # Get webhook info
            resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo")
            webhook_info = resp.json()
        
        # Get delivery stats
        now = datetime.now(timezone.utc)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        pending = await db.tg_delivery_outbox.count_documents({"status": "PENDING"})
        sent_today = await db.tg_delivery_outbox.count_documents({
            "status": "SENT",
            "sentAt": {"$gte": today}
        })
        failed_today = await db.tg_delivery_outbox.count_documents({
            "status": "FAILED",
            "createdAt": {"$gte": today}
        })
        
        # Alert stats
        alerts_sent = await db.geo_alert_log.count_documents({
            "sentAt": {"$gte": today}
        })
        
        return {
            "ok": True,
            "botConfigured": True,
            "botInfo": bot_info.get("result") if bot_info.get("ok") else None,
            "webhook": {
                "active": bool(webhook_info.get("result", {}).get("url")),
                "url": webhook_info.get("result", {}).get("url"),
                "pendingUpdates": webhook_info.get("result", {}).get("pending_update_count", 0),
                "lastError": webhook_info.get("result", {}).get("last_error_message"),
                "lastErrorDate": webhook_info.get("result", {}).get("last_error_date"),
            },
            "delivery": {
                "pending": pending,
                "sentToday": sent_today,
                "failedToday": failed_today,
                "alertsSentToday": alerts_sent
            }
        }
    except Exception as e:
        logger.error(f"Bot status error: {e}")
        return {"ok": False, "error": str(e)}


async def set_webhook(url: str) -> Dict[str, Any]:
    """Set bot webhook URL"""
    try:
        if not BOT_TOKEN:
            return {"ok": False, "error": "Bot token not configured"}
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": url, "allowed_updates": ["message", "callback_query"]}
            )
            return resp.json()
    except Exception as e:
        logger.error(f"Set webhook error: {e}")
        return {"ok": False, "error": str(e)}


async def delete_webhook() -> Dict[str, Any]:
    """Delete bot webhook"""
    try:
        if not BOT_TOKEN:
            return {"ok": False, "error": "Bot token not configured"}
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": False}
            )
            return resp.json()
    except Exception as e:
        logger.error(f"Delete webhook error: {e}")
        return {"ok": False, "error": str(e)}


async def send_test_message(db, chat_id: int, message: str = None) -> Dict[str, Any]:
    """Send test message to a user"""
    try:
        if not BOT_TOKEN:
            return {"ok": False, "error": "Bot token not configured"}
        
        text = message or "🔔 Test message from Geo Admin"
        
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML"
                }
            )
            return resp.json()
    except Exception as e:
        logger.error(f"Send test message error: {e}")
        return {"ok": False, "error": str(e)}


async def get_delivery_queue(db, status: str = "PENDING", limit: int = 50) -> Dict[str, Any]:
    """Get delivery queue items"""
    try:
        items = await db.tg_delivery_outbox.find(
            {"status": status},
            {"_id": 0}
        ).sort("nextAttemptAt", 1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": items, "count": len(items)}
    except Exception as e:
        logger.error(f"Delivery queue error: {e}")
        return {"ok": False, "error": str(e)}


async def retry_failed_deliveries(db) -> Dict[str, Any]:
    """Retry failed deliveries"""
    try:
        now = datetime.now(timezone.utc)
        
        result = await db.tg_delivery_outbox.update_many(
            {"status": "FAILED"},
            {
                "$set": {
                    "status": "PENDING",
                    "nextAttemptAt": now,
                    "attempts": 0
                }
            }
        )
        
        return {"ok": True, "retriedCount": result.modified_count}
    except Exception as e:
        logger.error(f"Retry failed error: {e}")
        return {"ok": False, "error": str(e)}
