"""
Geo Admin - Sessions Service
MTProto session management with encryption
"""
import os
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

# Encryption key for session strings
SESSION_ENCRYPTION_KEY = os.environ.get("SESSION_ENCRYPTION_KEY")
if not SESSION_ENCRYPTION_KEY:
    # Generate a key if not set (for development)
    SESSION_ENCRYPTION_KEY = Fernet.generate_key().decode()
    logger.warning("SESSION_ENCRYPTION_KEY not set, using generated key")

cipher = Fernet(SESSION_ENCRYPTION_KEY.encode() if isinstance(SESSION_ENCRYPTION_KEY, str) else SESSION_ENCRYPTION_KEY)


def encrypt_session(session_string: str) -> str:
    """Encrypt session string before storage"""
    return cipher.encrypt(session_string.encode()).decode()


def decrypt_session(encrypted: str) -> str:
    """Decrypt session string for use"""
    return cipher.decrypt(encrypted.encode()).decode()


async def get_sessions(db) -> Dict[str, Any]:
    """Get all MTProto sessions (without decrypted strings)"""
    try:
        sessions = await db.telegram_sessions.find(
            {},
            {
                "_id": 0,
                "encryptedSession": 0  # Never expose encrypted session
            }
        ).to_list(100)
        
        return {"ok": True, "items": sessions}
    except Exception as e:
        logger.error(f"Get sessions error: {e}")
        return {"ok": False, "error": str(e)}


async def add_session(
    db,
    name: str,
    session_string: str,
    api_id: int,
    api_hash: str,
    max_threads: int = 4,
    channels_limit: int = 40
) -> Dict[str, Any]:
    """Add new MTProto session"""
    try:
        # Validate session by connecting
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        try:
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            await client.connect()
            
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"ok": False, "error": "Session not authorized"}
            
            me = await client.get_me()
            await client.disconnect()
            
            session_user = {
                "id": me.id,
                "username": me.username,
                "firstName": me.first_name
            }
        except Exception as e:
            return {"ok": False, "error": f"Session validation failed: {str(e)}"}
        
        # Encrypt and store
        session_id = f"session_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc)
        
        doc = {
            "sessionId": session_id,
            "name": name,
            "encryptedSession": encrypt_session(session_string),
            "apiId": api_id,
            "apiHash": api_hash,
            "status": "idle",
            "maxThreads": max_threads,
            "channelsLimit": channels_limit,
            "channelsAssigned": 0,
            "activeThreads": 0,
            "rateLimitState": "ok",
            "lastActivity": None,
            "sessionUser": session_user,
            "createdAt": now,
            "updatedAt": now
        }
        
        await db.telegram_sessions.insert_one(doc)
        
        # Return without encrypted session
        doc.pop("encryptedSession")
        doc.pop("_id", None)
        
        return {"ok": True, "session": doc}
    except Exception as e:
        logger.error(f"Add session error: {e}")
        return {"ok": False, "error": str(e)}


async def remove_session(db, session_id: str) -> Dict[str, Any]:
    """Remove MTProto session"""
    try:
        result = await db.telegram_sessions.delete_one({"sessionId": session_id})
        return {"ok": True, "deleted": result.deleted_count > 0}
    except Exception as e:
        logger.error(f"Remove session error: {e}")
        return {"ok": False, "error": str(e)}


async def update_session_status(
    db,
    session_id: str,
    status: str,
    rate_limit_state: str = None
) -> Dict[str, Any]:
    """Update session status"""
    try:
        updates = {
            "status": status,
            "updatedAt": datetime.now(timezone.utc),
            "lastActivity": datetime.now(timezone.utc)
        }
        
        if rate_limit_state:
            updates["rateLimitState"] = rate_limit_state
        
        result = await db.telegram_sessions.update_one(
            {"sessionId": session_id},
            {"$set": updates}
        )
        
        return {"ok": True, "modified": result.modified_count > 0}
    except Exception as e:
        logger.error(f"Update session status error: {e}")
        return {"ok": False, "error": str(e)}


async def test_session(db, session_id: str) -> Dict[str, Any]:
    """Test if session is still valid"""
    try:
        session = await db.telegram_sessions.find_one({"sessionId": session_id})
        if not session:
            return {"ok": False, "error": "Session not found"}
        
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        
        decrypted = decrypt_session(session["encryptedSession"])
        
        client = TelegramClient(
            StringSession(decrypted),
            session["apiId"],
            session["apiHash"]
        )
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.disconnect()
            await update_session_status(db, session_id, "invalid")
            return {"ok": False, "error": "Session no longer authorized"}
        
        me = await client.get_me()
        await client.disconnect()
        
        await update_session_status(db, session_id, "idle", "ok")
        
        return {
            "ok": True,
            "valid": True,
            "user": {
                "id": me.id,
                "username": me.username,
                "firstName": me.first_name
            }
        }
    except Exception as e:
        logger.error(f"Test session error: {e}")
        return {"ok": False, "error": str(e)}


async def get_session_stats(db) -> Dict[str, Any]:
    """Get aggregated session statistics"""
    try:
        sessions = await db.telegram_sessions.find({}, {"_id": 0}).to_list(100)
        
        active = sum(1 for s in sessions if s.get("status") == "active")
        idle = sum(1 for s in sessions if s.get("status") == "idle")
        cooldown = sum(1 for s in sessions if s.get("status") == "cooldown")
        invalid = sum(1 for s in sessions if s.get("status") == "invalid")
        
        total_threads = sum(s.get("activeThreads", 0) for s in sessions)
        total_channels = sum(s.get("channelsAssigned", 0) for s in sessions)
        
        return {
            "ok": True,
            "totalSessions": len(sessions),
            "active": active,
            "idle": idle,
            "cooldown": cooldown,
            "invalid": invalid,
            "totalThreads": total_threads,
            "totalChannels": total_channels
        }
    except Exception as e:
        logger.error(f"Session stats error: {e}")
        return {"ok": False, "error": str(e)}
