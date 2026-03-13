"""
Telegram Intel - API Routes
Version: 1.0.0 (FROZEN)

FastAPI router with all public endpoints.
"""

from fastapi import APIRouter, Request, Response, Query
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..module import TelegramModule


def create_router(module: "TelegramModule") -> APIRouter:
    """
    Create FastAPI router for Telegram Intel Module.
    
    All routes are prefixed with /api/telegram-intel/
    """
    router = APIRouter(prefix="/api/telegram-intel", tags=["telegram-intel"])
    
    # ==========================================
    # HEALTH & VERSION
    # ==========================================
    
    @router.get("/health")
    async def health():
        from ..__version__ import VERSION
        return {
            "ok": True,
            "module": "telegram-intel",
            "version": VERSION,
            "runtime": {
                "mode": "live" if module.config.session_string else "mock",
                "connected": module._started
            }
        }
    
    @router.get("/version")
    async def version():
        """
        Get module version info.
        
        Returns:
            {"version": "1.0.0", "frozen": true, "module": "telegram-intel"}
        """
        return module.get_version_info()
    
    # ==========================================
    # FEED
    # ==========================================
    
    @router.get("/feed/v2")
    async def feed_v2(
        request: Request,
        response: Response,
        actorId: str = Query("default"),
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        windowDays: int = Query(7, ge=1, le=30)
    ):
        return await module.get_feed(actorId, page, limit, windowDays)
    
    @router.get("/feed/stats")
    async def feed_stats(actorId: str = "default", hours: int = 24):
        return await module.get_feed_stats(actorId, hours)
    
    @router.get("/feed/summary")
    async def feed_summary(hours: int = 24):
        return await module.get_feed_summary(hours)
    
    # ==========================================
    # CHANNEL
    # ==========================================
    
    @router.get("/channel/{username}/full")
    async def channel_full(username: str):
        return await module.get_channel(username)
    
    @router.get("/utility/list")
    async def channel_list(
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        sortBy: str = "utilityScore"
    ):
        return await module.get_channels(limit, offset, sortBy)
    
    # ==========================================
    # WATCHLIST
    # ==========================================
    
    @router.get("/watchlist")
    async def watchlist_get(actorId: str = "default"):
        return await module.get_watchlist(actorId)
    
    @router.post("/watchlist")
    async def watchlist_add(body: dict = None):
        username = (body or {}).get("username", "")
        actor_id = (body or {}).get("actorId", "a_public")
        return await module.add_to_watchlist(username, actor_id)
    
    @router.delete("/watchlist/{username}")
    async def watchlist_remove(username: str, actorId: str = "default"):
        return await module.remove_from_watchlist(username, actorId)
    
    # ==========================================
    # ALERTS
    # ==========================================
    
    @router.get("/alerts")
    async def alerts_get(actorId: str = "default", limit: int = 50):
        return await module.get_alerts(actorId, limit)
    
    # ==========================================
    # BOT
    # ==========================================
    
    @router.get("/bot/status")
    async def bot_status():
        return await module.get_bot_status()
    
    return router
