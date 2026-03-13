"""
Telegram Intel - Bot Service
Version: 1.0.0
"""

import logging
from typing import Any, Dict, Optional
import httpx

logger = logging.getLogger(__name__)


async def get_bot_status(db, bot_token: Optional[str] = None) -> Dict[str, Any]:
    """Get bot status and delivery stats"""
    if not bot_token:
        return {
            "ok": True,
            "botConfigured": False,
            "botInfo": None,
            "webhook": {"active": False},
            "delivery": {"linkedUsers": 0, "pendingMessages": 0, "sentMessages": 0, "failedMessages": 0},
            "requirements": {"webhookNeeded": True}
        }
    
    # Get bot info
    bot_info = None
    webhook_info = None
    
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            # Get bot info
            resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            data = resp.json()
            if data.get("ok"):
                bot_info = data.get("result", {})
            
            # Get webhook info
            resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getWebhookInfo")
            data = resp.json()
            if data.get("ok"):
                webhook_info = data.get("result", {})
    except Exception as e:
        logger.warning(f"Bot API error: {e}")
    
    # Get delivery stats
    linked_users = await db.tg_actor_links.count_documents({"provider": "telegram", "revokedAt": None})
    pending = await db.tg_delivery_outbox.count_documents({"status": "PENDING"})
    sent = await db.tg_delivery_outbox.count_documents({"status": "SENT"})
    failed = await db.tg_delivery_outbox.count_documents({"status": "FAILED"})
    
    webhook_active = bool(webhook_info and webhook_info.get("url"))
    
    return {
        "ok": True,
        "botConfigured": True,
        "botInfo": {
            "username": bot_info.get("username") if bot_info else None,
            "firstName": bot_info.get("first_name") if bot_info else None,
            "canJoinGroups": bot_info.get("can_join_groups") if bot_info else None
        },
        "webhook": {
            "active": webhook_active,
            "url": webhook_info.get("url") if webhook_info else None,
            "pendingUpdateCount": webhook_info.get("pending_update_count") if webhook_info else 0
        },
        "delivery": {
            "linkedUsers": linked_users,
            "pendingMessages": pending,
            "sentMessages": sent,
            "failedMessages": failed
        },
        "requirements": {
            "webhookNeeded": not webhook_active
        }
    }
