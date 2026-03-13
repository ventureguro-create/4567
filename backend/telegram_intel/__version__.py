"""
Telegram Intelligence Module
Version: 1.0.0
Status: FROZEN
"""

VERSION = "1.0.0"
FROZEN = True
MODULE_NAME = "telegram-intel"

def get_version_info():
    return {
        "version": VERSION,
        "frozen": FROZEN,
        "module": MODULE_NAME
    }
