"""
Telegram Intel - Alerts Service
Version: 1.0.0
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def get_alerts(db, actor_id: str = "default", limit: int = 50) -> Dict[str, Any]:
    """Get actor's alerts"""
    try:
        alerts = await db.tg_alerts.find(
            {"actorId": actor_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {
            "ok": True,
            "actorId": actor_id,
            "count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"Alerts error: {e}")
        return {"ok": False, "error": str(e), "alerts": [], "count": 0}


async def dispatch_alerts(db, bot_token: Optional[str] = None) -> Dict[str, Any]:
    """Dispatch pending alerts to linked users"""
    if not bot_token:
        return {"ok": False, "error": "Bot token not configured"}
    
    # Placeholder - actual implementation uses delivery_bot
    return {"ok": True, "dispatched": 0}
