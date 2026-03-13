"""
MTProto Client Module - Telethon + зашифрованные credentials
Production-grade with reconnect guard, keep-alive, and session protection

IMPORTANT RULES:
1. ONE instance per deployment environment
2. Do NOT run this session on multiple servers/containers
3. Do NOT use VPN on the host machine
4. Session is locked via MongoDB to prevent parallel usage
"""
import asyncio
import logging
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path
from cryptography.fernet import Fernet

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    FloodWaitError,
    ChannelPrivateError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
)

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).parent.parent

# Session state tracking
_session_state = {
    "connected": False,
    "authorized": False,
    "dc": None,
    "lastPing": None,
    "lastError": None,
    "reconnectCount": 0,
    "fingerprint": None,
    "lockAcquired": False
}


import os

def load_mtproto_credentials() -> Optional[Dict[str, Any]]:
    """Загрузить credentials из ENV или зашифрованного файла"""
    
    # Priority 1: Load from ENV (direct session string)
    env_session = os.environ.get('TG_SESSION_STRING')
    if env_session:
        logger.info("MTProto credentials loaded from ENV (TG_SESSION_STRING)")
        return {
            'SESSION_STRING': env_session,
            'API_ID': 2040,
            'API_HASH': 'b18441a1ff607e10a989891a5462e627'
        }
    
    # Priority 2: Load from encrypted file
    key_path = ROOT_DIR / '.secrets' / 'SESSION_KEY.txt'
    enc_path = ROOT_DIR / '.secrets' / 'mtproto_session.enc'
    
    if not key_path.exists() or not enc_path.exists():
        logger.error(f"MTProto credentials files not found: key={key_path.exists()}, enc={enc_path.exists()}")
        return None
    
    try:
        # Read key - support both "SESSION_KEY=xxx" and plain "xxx" formats
        key = None
        with open(key_path, 'r') as f:
            content = f.read().strip()
            if '=' in content:
                for line in content.split('\n'):
                    if 'SESSION_KEY=' in line or 'KEY=' in line:
                        key = line.split('=', 1)[1].strip()
                        break
            if not key:
                key = content.split('\n')[0].strip()
        
        if not key:
            logger.error("No key found in SESSION_KEY.txt")
            return None
        
        fernet = Fernet(key.encode())
        with open(enc_path, 'rb') as f:
            encrypted = f.read()
        
        decrypted = fernet.decrypt(encrypted)
        data = json.loads(decrypted.decode())
        logger.info(f"MTProto credentials loaded from encrypted file, API_ID={data.get('API_ID')}")
        return data
    except Exception as e:
        logger.error(f"Failed to load MTProto credentials: {e}")
        return None


CREDENTIALS = load_mtproto_credentials()

if CREDENTIALS:
    SESSION_STRING = CREDENTIALS.get('SESSION_STRING')
    API_ID = CREDENTIALS.get('API_ID')
    API_HASH = CREDENTIALS.get('API_HASH')
    logger.info("MTProto credentials loaded from encrypted file")
else:
    SESSION_STRING = None
    API_ID = None
    API_HASH = None
    logger.warning("MTProto credentials not available")


def get_session_state() -> Dict[str, Any]:
    """Get current session state for health endpoint"""
    return {
        **_session_state,
        "credentialsLoaded": CREDENTIALS is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


class MTProtoClient:
    """Singleton MTProto client using Telethon with reconnect support"""
    _instance = None
    _client: Optional[TelegramClient] = None
    _connected: bool = False
    _keep_alive_task: Optional[asyncio.Task] = None
    _reconnect_lock = asyncio.Lock() if asyncio else None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._reconnect_lock = asyncio.Lock()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'MTProtoClient':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def connect(self, retry_count: int = 3, db=None) -> bool:
        """Connect using credentials from encrypted file with retry logic.
        
        IMPORTANT RULES:
        - ONE session = ONE machine/container/IP
        - NO parallel launches
        - Validates lock before connecting
        """
        global _session_state
        
        if self._connected and self._client and self._client.is_connected():
            return True
        
        if not CREDENTIALS:
            logger.error("No MTProto credentials available")
            _session_state["lastError"] = "NO_CREDENTIALS"
            return False
        
        # Validate session guard if db is provided
        if db is not None:
            try:
                from telegram_lite.session_guard import validate_mtproto_startup, get_session_fingerprint
                fingerprint = get_session_fingerprint(SESSION_STRING)
                validation = await validate_mtproto_startup(db, SESSION_STRING)
                if not validation.get("ok"):
                    error_msg = validation.get("error", "UNKNOWN")
                    logger.error(f"Session guard blocked startup: {error_msg}")
                    _session_state["lastError"] = f"SESSION_GUARD: {error_msg}"
                    _session_state["lockAcquired"] = False
                    return False
                _session_state["lockAcquired"] = True
                _session_state["fingerprint"] = fingerprint
                logger.info(f"Session guard validated: fingerprint={fingerprint[:20]}...")
            except Exception as e:
                logger.warning(f"Session guard check failed (non-blocking): {e}")
        
        async with self._reconnect_lock:
            # Double-check after acquiring lock
            if self._connected and self._client and self._client.is_connected():
                return True
            
            for attempt in range(retry_count):
                try:
                    self._client = TelegramClient(
                        StringSession(SESSION_STRING),
                        API_ID,
                        API_HASH
                    )
                    
                    await self._client.connect()
                    
                    if not await self._client.is_user_authorized():
                        logger.error("Session not authorized")
                        _session_state["authorized"] = False
                        _session_state["lastError"] = "NOT_AUTHORIZED"
                        return False
                    
                    self._connected = True
                    me = await self._client.get_me()
                    
                    # Update session state
                    _session_state.update({
                        "connected": True,
                        "authorized": True,
                        "dc": getattr(self._client.session, 'dc_id', None),
                        "lastPing": datetime.now(timezone.utc).isoformat(),
                        "lastError": None,
                        "userId": me.id,
                        "username": me.username
                    })
                    
                    logger.info(f"Connected as: {me.first_name} (@{me.username or me.id})")
                    
                    # Start keep-alive task
                    self._start_keep_alive()
                    
                    return True
                    
                except Exception as e:
                    logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                    _session_state["lastError"] = str(e)
                    _session_state["reconnectCount"] += 1
                    
                    if attempt < retry_count - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            self._connected = False
            _session_state["connected"] = False
            return False
    
    def _start_keep_alive(self):
        """Start background keep-alive task"""
        if self._keep_alive_task and not self._keep_alive_task.done():
            return
        
        async def keep_alive_loop():
            while True:
                try:
                    await asyncio.sleep(300)  # 5 minutes
                    if self._client and self._connected:
                        me = await self._client.get_me()
                        _session_state["lastPing"] = datetime.now(timezone.utc).isoformat()
                        logger.debug(f"Keep-alive ping: {me.username}")
                except Exception as e:
                    logger.warning(f"Keep-alive error: {e}")
                    # Try to reconnect
                    await self._try_reconnect()
        
        try:
            self._keep_alive_task = asyncio.create_task(keep_alive_loop())
        except RuntimeError:
            pass  # No event loop
    
    async def _try_reconnect(self):
        """Attempt to reconnect after disconnect"""
        global _session_state
        
        logger.info("Attempting reconnect...")
        self._connected = False
        _session_state["connected"] = False
        
        success = await self.connect(retry_count=3)
        if success:
            logger.info("Reconnect successful")
        else:
            logger.error("Reconnect failed")
    
    async def disconnect(self):
        """Disconnect the client"""
        global _session_state
        
        if self._keep_alive_task:
            self._keep_alive_task.cancel()
            self._keep_alive_task = None
        
        if self._client and self._connected:
            await self._client.disconnect()
            self._connected = False
            _session_state["connected"] = False
            logger.info("Disconnected from Telegram")
    
    async def is_connected(self) -> bool:
        """Check if client is connected"""
        return self._connected and self._client is not None and self._client.is_connected()
    
    async def health_check(self) -> Dict[str, Any]:
        """Detailed health check for monitoring"""
        global _session_state
        
        health = {
            "connected": False,
            "authorized": False,
            "dc": None,
            "lastPing": _session_state.get("lastPing"),
            "lastError": _session_state.get("lastError"),
            "reconnectCount": _session_state.get("reconnectCount", 0),
            "credentialsLoaded": CREDENTIALS is not None
        }
        
        if self._client and self._connected:
            try:
                me = await self._client.get_me()
                health.update({
                    "connected": True,
                    "authorized": True,
                    "dc": getattr(self._client.session, 'dc_id', None),
                    "lastPing": datetime.now(timezone.utc).isoformat(),
                    "userId": me.id,
                    "username": me.username
                })
                _session_state["lastPing"] = health["lastPing"]
            except Exception as e:
                health["lastError"] = str(e)
        
        return health
    
    async def get_channel_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Fetch channel/group information"""
        if not await self.connect():
            return {'error': 'NOT_CONNECTED'}
        
        clean_username = username.lower().replace('@', '').strip()
        
        try:
            entity = await self._client.get_entity(clean_username)
            
            # Get full channel info for members count
            full = await self._client.get_participants(entity, limit=0)
            members_count = full.total if hasattr(full, 'total') else 0
            
            is_channel = hasattr(entity, 'broadcast') and entity.broadcast
            is_megagroup = hasattr(entity, 'megagroup') and entity.megagroup
            
            return {
                'username': clean_username,
                'title': getattr(entity, 'title', clean_username),
                'about': getattr(entity, 'about', '') or '',
                'participantsCount': members_count,
                'isChannel': is_channel,
                'isMegagroup': is_megagroup,
                'photoId': getattr(entity.photo, 'photo_id', None) if hasattr(entity, 'photo') and entity.photo else None,
            }
            
        except ChannelPrivateError:
            logger.warning(f"Channel {clean_username} is private")
            return {'error': 'PRIVATE', 'username': clean_username}
            
        except UsernameNotOccupiedError:
            logger.warning(f"Username {clean_username} not found")
            return {'error': 'NOT_FOUND', 'username': clean_username}
            
        except UsernameInvalidError:
            logger.warning(f"Invalid username: {clean_username}")
            return {'error': 'INVALID', 'username': clean_username}
            
        except FloodWaitError as e:
            logger.error(f"Flood wait: {e.seconds}s")
            return {'error': 'FLOOD_WAIT', 'seconds': e.seconds}
            
        except Exception as e:
            logger.error(f"Error fetching channel {clean_username}: {e}")
            return {'error': 'UNKNOWN', 'message': str(e)}
    
    async def download_profile_photo(self, username: str, save_path: str = None) -> Optional[str]:
        """
        Download channel/user profile photo
        Returns: path to saved file or None
        """
        if not await self.connect():
            return None
        
        clean_username = username.lower().replace('@', '').strip()
        
        if not save_path:
            save_path = f"/app/backend/public/tg/avatars/{clean_username}.jpg"
        
        try:
            entity = await self._client.get_entity(clean_username)
            
            # Check if entity has photo
            if not hasattr(entity, 'photo') or not entity.photo:
                logger.info(f"No photo for {clean_username}")
                return None
            
            # Download photo
            result = await self._client.download_profile_photo(
                entity,
                file=save_path
            )
            
            if result:
                logger.info(f"Downloaded avatar for {clean_username}: {save_path}")
                # Return API URL format
                return f"/api/telegram-intel/avatars/{clean_username}.jpg"
            
            return None
            
        except Exception as e:
            logger.error(f"Error downloading avatar for {clean_username}: {e}")
            return None
    
    async def get_channel_messages(
        self, 
        username: str, 
        limit: int = 100,
        download_media: bool = False,
        db = None
    ) -> Optional[List[Dict[str, Any]]]:
        """Fetch recent messages from a channel with optional media download"""
        if not await self.connect():
            return None
        
        clean_username = username.lower().replace('@', '').strip()
        
        try:
            entity = await self._client.get_entity(clean_username)
            messages = []
            
            async for msg in self._client.iter_messages(entity, limit=min(limit, 1000)):
                # Extract reactions with proper normalization
                reactions = {"total": 0, "items": []}
                if hasattr(msg, 'reactions') and msg.reactions:
                    items = []
                    total = 0
                    for r in getattr(msg.reactions, 'results', []):
                        emoji = None
                        # Handle different reaction types
                        reaction_obj = getattr(r, 'reaction', None)
                        if reaction_obj:
                            emoji = getattr(reaction_obj, 'emoticon', None) or str(reaction_obj)
                        count = getattr(r, 'count', 0) or 0
                        if emoji and count > 0:
                            items.append({"emoji": emoji, "count": count})
                            total += count
                    # Sort DESC by count
                    items.sort(key=lambda x: x["count"], reverse=True)
                    reactions = {"total": total, "items": items}
                
                # Extract replies properly
                replies_count = 0
                if hasattr(msg, 'replies') and msg.replies:
                    replies_count = getattr(msg.replies, 'replies', 0) or \
                                   getattr(msg.replies, 'replies_count', 0) or 0
                
                msg_data = {
                    'messageId': msg.id,
                    'date': msg.date.isoformat() if msg.date else None,
                    'text': msg.text or '',
                    'views': msg.views or 0,
                    'forwards': msg.forwards or 0,
                    'replies': replies_count,
                    'reactions': reactions,
                    'hasMedia': msg.media is not None,
                    'mediaType': None,
                    'mediaLocalPath': None,
                    'mediaSize': None,
                    'mediaDownloaded': False,
                }
                
                # Determine media type
                if msg.photo:
                    msg_data['mediaType'] = 'photo'
                elif msg.video:
                    msg_data['mediaType'] = 'video'
                elif msg.document:
                    msg_data['mediaType'] = 'document'
                
                # Download media if requested (with Media Engine PRO integration)
                if download_media and msg_data['hasMedia'] and msg_data['mediaType'] in ('photo', 'video'):
                    media_path = await self.download_media_safe(msg, clean_username, db=db)
                    if media_path:
                        msg_data['mediaLocalPath'] = media_path
                        msg_data['mediaDownloaded'] = True
                        # Get file size
                        try:
                            import os
                            full_path = f"/app/backend/public{media_path}"
                            if os.path.exists(full_path):
                                msg_data['mediaSize'] = os.path.getsize(full_path)
                        except:
                            pass
                
                messages.append(msg_data)
            
            return messages
            
        except FloodWaitError as e:
            logger.error(f"Flood wait on messages: {e.seconds}s")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching messages from {clean_username}: {e}")
            return None
    
    async def get_message_by_id(self, username: str, message_id: int):
        """
        Fetch single message by ID for media backfill.
        Returns raw Telethon message object or None.
        """
        if not await self.connect():
            return None
        
        clean_username = username.lower().replace('@', '').strip()
        
        try:
            entity = await self._client.get_entity(clean_username)
            messages = await self._client.get_messages(entity, ids=[message_id])
            
            if messages and len(messages) > 0:
                return messages[0]
            return None
            
        except FloodWaitError as e:
            logger.error(f"Flood wait on get_message_by_id: {e.seconds}s")
            raise  # Re-raise for backfill worker to handle
            
        except Exception as e:
            logger.error(f"Error fetching message {clean_username}/{message_id}: {e}")
            return None
    
    async def download_media_safe(self, message, username: str, db=None, max_size_mb: int = 20) -> Optional[str]:
        """
        Download photo/video from message safely with Media Engine PRO integration.
        Returns: relative URL path or None
        
        Features:
        - Size guard
        - Dedupe via tg_media_assets
        - Disk guard
        """
        import os
        from datetime import datetime, timezone
        
        if not message or not message.media:
            return None
        
        if not message.photo and not message.video:
            return None
        
        kind = "photo" if message.photo else "video"
        ext = "jpg" if kind == "photo" else "mp4"
        
        # Check file size limit
        file_size = None
        if message.file and message.file.size:
            file_size = message.file.size
            if file_size > max_size_mb * 1024 * 1024:
                logger.info(f"Media too large ({file_size / 1024 / 1024:.1f}MB), skipping")
                return None
        
        # Create folder structure
        media_root = "/app/backend/public/tg/media"
        folder = os.path.join(media_root, username)
        os.makedirs(folder, exist_ok=True)
        
        filename = f"{message.id}.{ext}"
        file_path = os.path.join(folder, filename)
        relative_url = f"/tg/media/{username}/{filename}"
        
        # Dedupe check via tg_media_assets (if db available)
        if db is not None:
            existing = await db.tg_media_assets.find_one({
                "username": username,
                "messageId": message.id,
                "kind": kind,
                "status": "READY"
            })
            
            if existing and os.path.exists(file_path):
                # Update lastAccessAt
                await db.tg_media_assets.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"lastAccessAt": datetime.now(timezone.utc)}}
                )
                logger.debug(f"Media cached: {relative_url}")
                return relative_url
        
        # Skip if file exists (fallback dedupe)
        if os.path.exists(file_path):
            logger.debug(f"Media file exists: {file_path}")
            return relative_url
        
        try:
            await self._client.download_media(message, file=file_path)
            
            actual_size = os.path.getsize(file_path) if os.path.exists(file_path) else file_size
            
            # Get dimensions/duration
            w, h, duration = None, None, None
            if message.photo and hasattr(message.photo, 'sizes') and message.photo.sizes:
                largest = message.photo.sizes[-1]
                w = getattr(largest, 'w', None)
                h = getattr(largest, 'h', None)
            if message.video:
                duration = getattr(message.video, 'duration', None)
            
            # Register in tg_media_assets (if db available)
            if db is not None:
                now = datetime.now(timezone.utc)
                await db.tg_media_assets.update_one(
                    {"username": username, "messageId": message.id, "kind": kind},
                    {
                        "$set": {
                            "username": username,
                            "messageId": message.id,
                            "kind": kind,
                            "localPath": file_path,
                            "url": relative_url,
                            "size": actual_size,
                            "w": w,
                            "h": h,
                            "duration": duration,
                            "mime": "image/jpeg" if kind == "photo" else "video/mp4",
                            "status": "READY",
                            "lastAccessAt": now,
                        },
                        "$setOnInsert": {
                            "createdAt": now,
                            "pinned": False
                        }
                    },
                    upsert=True
                )
            
            logger.info(f"Downloaded media: {relative_url} ({actual_size/1024:.1f}KB)")
            return relative_url
            
        except FloodWaitError as e:
            logger.warning(f"Flood wait on media download: {e.seconds}s")
            return None
            
        except Exception as e:
            logger.error(f"Error downloading media for {username}/{message.id}: {e}")
            
            # Register as failed (if db available)
            if db is not None:
                await db.tg_media_assets.update_one(
                    {"username": username, "messageId": message.id, "kind": kind},
                    {
                        "$set": {
                            "status": "FAILED",
                            "error": str(e)[:200],
                            "lastAccessAt": datetime.now(timezone.utc)
                        }
                    },
                    upsert=True
                )
            return None


def get_mtproto_client() -> MTProtoClient:
    """Get the singleton MTProto client instance"""
    return MTProtoClient.get_instance()


class MTProtoConnection:
    """Context manager for MTProto connections"""
    
    def __init__(self):
        self.client = get_mtproto_client()
    
    async def __aenter__(self) -> MTProtoClient:
        await self.client.connect()
        return self.client
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
