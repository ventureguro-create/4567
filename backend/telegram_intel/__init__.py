"""
Telegram Intelligence Module
Version: 1.0.0 (FROZEN)

Standalone, Extractable, Contract-Safe Module

Usage:
    from telegram_intel import TelegramModule
    
    config = TelegramConfig(
        mongo_uri="mongodb://localhost:27017",
        session_string="...",
        bot_token="..."
    )
    
    telegram = TelegramModule(config)
    app.include_router(telegram.router)
    
    # Start background tasks
    await telegram.start()
    
    # On shutdown
    await telegram.stop()
"""

from .__version__ import VERSION, FROZEN, get_version_info
from .contracts import TelegramConfig
from .module import TelegramModule

__all__ = [
    "TelegramModule",
    "TelegramConfig",
    "VERSION",
    "FROZEN",
    "get_version_info",
]

__version__ = VERSION
