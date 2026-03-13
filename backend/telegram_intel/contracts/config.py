"""
Telegram Intel - Configuration Contract
Version: 1.0.0

Defines all required configuration for the module.

SECURITY: session_string must NEVER be:
- Logged
- Written to database
- Written to files
- Exposed in API responses
"""

from pydantic import BaseModel, Field
from typing import Optional


class TelegramConfig(BaseModel):
    """
    Configuration required to run Telegram Intel Module
    
    Pass this to TelegramModule(config) on initialization.
    All fields with defaults are optional.
    
    SECURITY WARNING:
    - session_string contains sensitive authentication data
    - DO NOT log session_string under any circumstances
    - DO NOT persist session_string to database
    - DO NOT expose session_string in API responses
    """
    
    # === REQUIRED ===
    mongo_uri: str = Field(..., description="MongoDB connection string")
    db_name: str = Field(default="telegram_intel", description="Database name")
    
    # === MTProto (required for live data) ===
    # SECURITY: Never log or persist this value
    session_string: Optional[str] = Field(default=None, description="Telethon session string - SENSITIVE")
    api_id: Optional[int] = Field(default=None, description="Telegram API ID")
    api_hash: Optional[str] = Field(default=None, description="Telegram API Hash")
    
    # === Bot (required for delivery) ===
    bot_token: Optional[str] = Field(default=None, description="Telegram Bot Token")
    
    # === Storage ===
    media_path: str = Field(default="/data/telegram_media", description="Path for media files")
    
    # === URLs ===
    public_base_url: Optional[str] = Field(default=None, description="Public URL for media access")
    
    # === LLM (optional, for AI summary) ===
    llm_api_key: Optional[str] = Field(default=None, description="LLM API key for summaries")
    
    # === Scheduler ===
    scheduler_enabled: bool = Field(default=True, description="Enable background scheduler")
    scheduler_interval_minutes: int = Field(default=15, description="Scheduler tick interval")
    
    # === Limits ===
    max_channels: int = Field(default=100, description="Max channels to monitor")
    max_posts_per_channel: int = Field(default=100, description="Max posts to store per channel")
    media_max_size_mb: int = Field(default=20, description="Max media file size to download")
    
    class Config:
        env_prefix = "TG_"
    
    def __repr__(self):
        """Safe repr - never show session_string"""
        return f"TelegramConfig(db={self.db_name}, session={'***' if self.session_string else None}, bot={'***' if self.bot_token else None})"
    
    def __str__(self):
        """Safe str - never show session_string"""
        return self.__repr__()
    
    class Config:
        env_prefix = "TG_"


# Environment contract - required variables
ENV_CONTRACT = """
# Telegram Intel Module - Required Environment Variables
# Version: 1.0.0

# === Database (REQUIRED) ===
MONGO_URL=mongodb://localhost:27017
TG_DB_NAME=telegram_intel

# === MTProto (REQUIRED for live data) ===
TG_SESSION_STRING=
TG_API_ID=
TG_API_HASH=

# === Bot (REQUIRED for delivery) ===
TG_BOT_TOKEN=

# === Storage ===
TG_MEDIA_PATH=/data/telegram_media

# === Public URL ===
PUBLIC_BASE_URL=https://yourdomain.com

# === LLM (OPTIONAL) ===
EMERGENT_LLM_KEY=
OPENAI_API_KEY=
"""
