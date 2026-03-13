"""
Geo Admin - Dashboard Service
Executive metrics for the admin panel
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)


async def get_dashboard_stats(db) -> Dict[str, Any]:
    """Get executive dashboard statistics"""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    
    try:
        # User metrics
        total_users = await db.geo_bot_users.count_documents({})
        radar_enabled = await db.geo_bot_users.count_documents({"radarEnabled": True})
        with_location = await db.geo_bot_users.count_documents({"lastLat": {"$ne": None}})
        
        # Alert metrics
        alerts_today = await db.geo_alert_log.count_documents({
            "sentAt": {"$gte": today_start}
        })
        alerts_failed = await db.geo_alert_log.count_documents({
            "status": "FAILED",
            "createdAt": {"$gte": today_start}
        })
        
        # Signal metrics
        signals_today = await db.tg_geo_events.count_documents({
            "createdAt": {"$gte": today_start}
        })
        signals_24h = await db.tg_geo_events.count_documents({
            "createdAt": {"$gte": last_24h}
        })
        
        # User reports
        reports_today = await db.geo_user_reports.count_documents({
            "createdAt": {"$gte": today_start}
        })
        
        # Channel metrics
        active_channels = await db.geo_channels.count_documents({"enabled": True})
        total_channels = await db.geo_channels.count_documents({})
        
        # Telegram Intel channels
        tg_channels = await db.tg_channel_states.count_documents({})
        tg_posts_24h = await db.tg_posts.count_documents({
            "date": {"$gte": last_24h.isoformat()}
        })
        
        # MTProto session status
        mtproto_status = "disconnected"
        try:
            from telegram_lite.mtproto_client import get_session_state
            state = get_session_state()
            mtproto_status = "connected" if state.get("connected") else "disconnected"
        except:
            pass
        
        # Bot delivery stats
        delivery_pending = await db.tg_delivery_outbox.count_documents({"status": "PENDING"})
        delivery_sent = await db.tg_delivery_outbox.count_documents({"status": "SENT"})
        delivery_failed = await db.tg_delivery_outbox.count_documents({"status": "FAILED"})
        
        return {
            "ok": True,
            "timestamp": now.isoformat(),
            "users": {
                "total": total_users,
                "radarEnabled": radar_enabled,
                "withLocation": with_location,
            },
            "alerts": {
                "sentToday": alerts_today,
                "failedToday": alerts_failed,
            },
            "signals": {
                "today": signals_today,
                "last24h": signals_24h,
                "reportsToday": reports_today,
            },
            "channels": {
                "active": active_channels,
                "total": total_channels,
                "telegramIntel": tg_channels,
            },
            "parsing": {
                "mtprotoStatus": mtproto_status,
                "posts24h": tg_posts_24h,
            },
            "delivery": {
                "pending": delivery_pending,
                "sent": delivery_sent,
                "failed": delivery_failed,
            }
        }
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return {"ok": False, "error": str(e)}
