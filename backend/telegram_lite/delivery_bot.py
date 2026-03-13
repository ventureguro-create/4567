"""
Telegram Bot Delivery Layer - Task 4
Production-grade notification system with:
- Actor linking via Telegram Bot
- Outbox queue for reliable delivery
- Rate limiting and retry logic
- Alert distribution to linked users
- Webhook with secret token verification
"""
import os
import secrets
import asyncio
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

# Config from ENV
BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '')
BOT_USERNAME = os.environ.get('TG_BOT_USERNAME', '')
WEBHOOK_SECRET = os.environ.get('TG_WEBHOOK_SECRET', '')
LINK_CODE_TTL_MIN = int(os.environ.get('TG_LINK_CODE_TTL_MIN', '30'))
SEND_RPS = int(os.environ.get('TG_SEND_RPS', '20'))

# Generate webhook secret if not set
if not WEBHOOK_SECRET and BOT_TOKEN:
    WEBHOOK_SECRET = hashlib.sha256(f"{BOT_TOKEN}_webhook_secret".encode()).hexdigest()[:32]


def utcnow():
    return datetime.utcnow()


def verify_webhook_secret(header_secret: str) -> bool:
    """Verify webhook secret token from Telegram"""
    if not WEBHOOK_SECRET:
        return True  # No secret configured, allow all
    return header_secret == WEBHOOK_SECRET


async def ensure_delivery_indexes(db):
    """Create indexes for delivery collections"""
    try:
        # tg_actor_links
        await db.tg_actor_links.create_index(
            [("actorId", 1), ("provider", 1)],
            unique=True
        )
        await db.tg_actor_links.create_index(
            [("tgChatId", 1), ("provider", 1)],
            unique=True,
            sparse=True
        )
        
        # tg_link_codes
        await db.tg_link_codes.create_index([("code", 1)], unique=True)
        await db.tg_link_codes.create_index(
            [("expiresAt", 1)],
            expireAfterSeconds=0  # TTL index
        )
        
        # tg_delivery_outbox
        await db.tg_delivery_outbox.create_index([("status", 1), ("nextAttemptAt", 1)])
        await db.tg_delivery_outbox.create_index([("dedupeKey", 1)], unique=True)
        await db.tg_delivery_outbox.create_index([("actorId", 1), ("createdAt", -1)])
        
        logger.info("Delivery indexes created")
    except Exception as e:
        logger.warning(f"Delivery index warning: {e}")


# ============== Link Code Management ==============

def generate_link_code() -> str:
    """Generate unique link code"""
    return "lc_" + secrets.token_hex(12)


async def create_link_code(db, actor_id: str) -> Dict[str, Any]:
    """Create new Telegram link code for actor"""
    code = generate_link_code()
    now = utcnow()
    expires_at = now + timedelta(minutes=LINK_CODE_TTL_MIN)
    
    await db.tg_link_codes.insert_one({
        "code": code,
        "actorId": actor_id,
        "createdAt": now,
        "expiresAt": expires_at,
        "usedAt": None
    })
    
    # Build bot start URL
    url = f"https://t.me/{BOT_USERNAME}?start={code}" if BOT_USERNAME else None
    
    return {
        "code": code,
        "url": url,
        "expiresAt": expires_at.isoformat()
    }


async def validate_and_use_link_code(db, code: str, tg_user_id: int, tg_chat_id: int, tg_username: str = None) -> Optional[str]:
    """
    Validate link code and create actor link.
    Returns actor_id if successful, None otherwise.
    """
    now = utcnow()
    
    # Find valid code
    record = await db.tg_link_codes.find_one({
        "code": code,
        "usedAt": None,
        "expiresAt": {"$gt": now}
    })
    
    if not record:
        return None
    
    actor_id = record["actorId"]
    
    # Mark code as used
    await db.tg_link_codes.update_one(
        {"code": code},
        {"$set": {"usedAt": now}}
    )
    
    # Create/update actor link
    await db.tg_actor_links.update_one(
        {"actorId": actor_id, "provider": "telegram"},
        {
            "$set": {
                "actorId": actor_id,
                "provider": "telegram",
                "tgUserId": tg_user_id,
                "tgChatId": tg_chat_id,
                "tgUsername": tg_username,
                "linkedAt": now,
                "revokedAt": None
            }
        },
        upsert=True
    )
    
    logger.info(f"Actor {actor_id} linked to Telegram chat {tg_chat_id}")
    
    return actor_id


async def get_actor_link_status(db, actor_id: str) -> Dict[str, Any]:
    """Get actor's Telegram link status"""
    link = await db.tg_actor_links.find_one(
        {"actorId": actor_id, "provider": "telegram", "revokedAt": None},
        {"_id": 0}
    )
    
    return {
        "linked": link is not None,
        "tgUsername": link.get("tgUsername") if link else None,
        "linkedAt": link.get("linkedAt").isoformat() if link and link.get("linkedAt") else None
    }


async def revoke_actor_link(db, actor_id: str) -> bool:
    """Revoke actor's Telegram link"""
    result = await db.tg_actor_links.update_one(
        {"actorId": actor_id, "provider": "telegram", "revokedAt": None},
        {"$set": {"revokedAt": utcnow()}}
    )
    return result.modified_count > 0


# ============== Telegram Bot API ==============

async def tg_send_message(chat_id: int, text: str, parse_mode: str = "HTML", reply_markup: dict = None) -> Dict[str, Any]:
    """Send message via Telegram Bot API"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not configured"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text[:4096],  # Telegram limit
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload)
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"TG API error: {e}")
            return {"ok": False, "error": str(e)}


# ============== Webhook Management ==============

async def set_webhook(webhook_url: str) -> Dict[str, Any]:
    """Set Telegram Bot webhook URL with secret token"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not configured"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
    
    payload = {
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": False
    }
    
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json=payload)
            data = response.json()
            logger.info(f"Webhook set: {data}")
            return data
        except Exception as e:
            logger.error(f"Set webhook error: {e}")
            return {"ok": False, "error": str(e)}


async def delete_webhook() -> Dict[str, Any]:
    """Delete Telegram Bot webhook"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not configured"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.post(url, json={"drop_pending_updates": False})
            data = response.json()
            logger.info(f"Webhook deleted: {data}")
            return data
        except Exception as e:
            logger.error(f"Delete webhook error: {e}")
            return {"ok": False, "error": str(e)}


async def get_webhook_info() -> Dict[str, Any]:
    """Get current webhook info"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not configured"}
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getWebhookInfo"
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            response = await client.get(url)
            data = response.json()
            return data
        except Exception as e:
            logger.error(f"Get webhook info error: {e}")
            return {"ok": False, "error": str(e)}
            logger.error(f"TG API error: {e}")
            return {"ok": False, "error": str(e)}


# ============== Bot Webhook Handler ==============

async def handle_bot_update(db, update: dict) -> Dict[str, Any]:
    """
    Handle incoming Telegram Bot update (webhook).
    Processes /start commands for linking.
    """
    message = update.get("message") or update.get("edited_message")
    if not message:
        return {"ok": True}
    
    chat_id = message.get("chat", {}).get("id")
    from_user = message.get("from", {})
    text = message.get("text", "")
    
    if not chat_id:
        return {"ok": True}
    
    # Handle /start <code>
    if text.startswith("/start"):
        parts = text.split()
        
        if len(parts) < 2:
            # No code - skip, let Geo Radar Bot handle plain /start
            return {"ok": True}
        
        code = parts[1]
        
        # Skip if code is a referral (ref_) - Geo Radar Bot handles those
        if code.startswith("ref_"):
            return {"ok": True}
        
        actor_id = await validate_and_use_link_code(
            db,
            code,
            tg_user_id=from_user.get("id"),
            tg_chat_id=chat_id,
            tg_username=from_user.get("username")
        )
        
        if actor_id:
            await tg_send_message(
                chat_id,
                "✅ Аккаунт успешно связан!\n\nТеперь ты будешь получать уведомления по избранным каналам."
            )
        else:
            await tg_send_message(
                chat_id,
                "❌ Ссылка недействительна или уже использована.\n\nСгенерируй новую на платформе."
            )
        
        return {"ok": True}
    
    # Handle /help
    if text == "/help":
        await tg_send_message(
            chat_id,
            "📋 <b>Команды:</b>\n\n"
            "/start &lt;code&gt; — привязать аккаунт\n"
            "/help — показать справку\n\n"
            "Для управления уведомлениями используй платформу."
        )
        return {"ok": True}
    
    # Handle /unlink
    if text == "/unlink":
        # Find actor by chat_id and revoke
        link = await db.tg_actor_links.find_one({
            "tgChatId": chat_id,
            "provider": "telegram",
            "revokedAt": None
        })
        
        if link:
            await revoke_actor_link(db, link["actorId"])
            await tg_send_message(chat_id, "✅ Аккаунт отвязан. Уведомления больше не будут приходить.")
        else:
            await tg_send_message(chat_id, "❌ Аккаунт не привязан.")
        
        return {"ok": True}
    
    return {"ok": True}


# ============== Delivery Outbox ==============

def hash_dedupe_key(s: str) -> str:
    """Create consistent hash for deduplication"""
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:32]


async def enqueue_telegram_message(
    db,
    actor_id: str,
    tg_chat_id: int,
    message_type: str,
    payload: Dict[str, Any],
    dedupe_key: str = None
) -> Dict[str, Any]:
    """
    Add message to delivery outbox for reliable sending.
    Deduplication prevents duplicate sends.
    """
    now = utcnow()
    
    if not dedupe_key:
        dedupe_key = hash_dedupe_key(f"{actor_id}:{tg_chat_id}:{message_type}:{payload.get('text', '')[:100]}")
    
    doc = {
        "actorId": actor_id,
        "provider": "telegram",
        "tgChatId": tg_chat_id,
        "type": message_type,
        "payload": payload,
        "dedupeKey": dedupe_key,
        "status": "PENDING",
        "attempts": 0,
        "nextAttemptAt": now,
        "createdAt": now,
        "sentAt": None,
        "lastError": None
    }
    
    try:
        await db.tg_delivery_outbox.insert_one(doc)
        return {"ok": True, "queued": True}
    except Exception as e:
        # Duplicate = already queued
        if "duplicate" in str(e).lower() or "11000" in str(e):
            return {"ok": True, "queued": False, "deduped": True}
        raise


async def run_delivery_worker(db, max_batch: int = 50) -> Dict[str, Any]:
    """
    Process outbox queue - send pending messages.
    Respects rate limits and implements retry with backoff.
    """
    now = utcnow()
    
    batch = await db.tg_delivery_outbox.find({
        "status": "PENDING",
        "nextAttemptAt": {"$lte": now}
    }).sort("nextAttemptAt", 1).limit(max_batch).to_list(max_batch)
    
    if not batch:
        return {"ok": True, "sent": 0, "failed": 0}
    
    delay_ms = max(50, 1000 // SEND_RPS)
    sent = 0
    failed = 0
    
    for item in batch:
        try:
            payload = item.get("payload", {})
            result = await tg_send_message(
                chat_id=item["tgChatId"],
                text=payload.get("text", ""),
                parse_mode=payload.get("parseMode", "HTML"),
                reply_markup=payload.get("replyMarkup")
            )
            
            if result.get("ok"):
                await db.tg_delivery_outbox.update_one(
                    {"_id": item["_id"]},
                    {"$set": {"status": "SENT", "sentAt": utcnow(), "lastError": None}}
                )
                sent += 1
            else:
                raise Exception(result.get("description", "Unknown error"))
                
        except Exception as e:
            attempts = item.get("attempts", 0) + 1
            backoff = min(3600, 60 * (2 ** min(attempts, 6)))  # Max 1 hour
            next_attempt = utcnow() + timedelta(seconds=backoff)
            
            status = "FAILED" if attempts >= 5 else "PENDING"
            
            await db.tg_delivery_outbox.update_one(
                {"_id": item["_id"]},
                {
                    "$set": {
                        "attempts": attempts,
                        "lastError": str(e)[:500],
                        "nextAttemptAt": next_attempt,
                        "status": status
                    }
                }
            )
            
            if status == "FAILED":
                failed += 1
        
        await asyncio.sleep(delay_ms / 1000)
    
    logger.info(f"Delivery worker: sent {sent}, failed {failed}")
    
    return {"ok": True, "sent": sent, "failed": failed}


# ============== Alert Distribution ==============

async def distribute_alerts_to_telegram(db, limit: int = 200) -> Dict[str, Any]:
    """
    Find pending alerts and queue them for delivery to linked actors.
    Only sends to actors who:
    - Have linked Telegram
    - Have the alert's channel in their watchlist
    """
    # Get active Telegram links
    links = await db.tg_actor_links.find({
        "provider": "telegram",
        "revokedAt": None
    }).to_list(1000)
    
    if not links:
        return {"ok": True, "queued": 0}
    
    queued = 0
    
    for link in links:
        actor_id = link["actorId"]
        tg_chat_id = link["tgChatId"]
        
        # Get actor's watchlist usernames
        watchlist = await db.tg_watchlist.find(
            {"actorId": actor_id},
            {"_id": 0, "username": 1}
        ).to_list(500)
        
        usernames = [w["username"] for w in watchlist]
        if not usernames:
            continue
        
        # Find undelivered alerts for these channels
        alerts = await db.tg_alerts.find({
            "username": {"$in": usernames},
            "status": {"$ne": "DELIVERED"}
        }).sort("createdAt", -1).limit(limit).to_list(limit)
        
        for alert in alerts:
            dedupe_key = f"alert:{alert.get('type', 'UNKNOWN')}:{alert.get('username', '')}:{str(alert.get('_id', ''))}"
            
            # Build message text
            text = (
                f"⚡ <b>{alert.get('type', 'Alert')}</b>\n"
                f"Канал: <b>@{alert.get('username', 'unknown')}</b>\n"
            )
            
            if alert.get("message"):
                text += f"\n{alert['message'][:500]}"
            
            if alert.get("url"):
                text += f"\n\n🔗 {alert['url']}"
            
            result = await enqueue_telegram_message(
                db,
                actor_id=actor_id,
                tg_chat_id=tg_chat_id,
                message_type="ALERT",
                payload={"text": text, "parseMode": "HTML"},
                dedupe_key=hash_dedupe_key(dedupe_key)
            )
            
            if result.get("queued"):
                queued += 1
                # Mark alert as delivered
                await db.tg_alerts.update_one(
                    {"_id": alert["_id"]},
                    {"$set": {"status": "DELIVERED", "deliveredAt": utcnow()}}
                )
    
    logger.info(f"Alert distribution: queued {queued} messages")
    
    return {"ok": True, "queued": queued}
