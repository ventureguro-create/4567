"""
Geo Intel API Router
All endpoints for the Geo/Radar module
"""
import os
import json
import logging
import uuid
import base64
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Query, HTTPException, Request, UploadFile, File, Form
from typing import Optional

from .services.aggregator import get_map_points, get_top_places, get_heatmap_data, get_event_types_stats
from .services.proximity import get_nearby_events, evaluate_radar_alert
from .services.summary import generate_summary
from .services.builder import build_geo_events_for_channel, rebuild_all_channels
from .services.stats import get_place_stats, get_hourly_stats, get_weekday_stats, get_full_stats
from .services.predictor import predict_hotspots, get_place_prediction
from .services.subscriptions import (
    create_subscription, update_location, unsubscribe, 
    get_subscription, get_active_subscriptions
)
from .services.notifier import send_test_alert, format_proximity_alert
from .services.bot import start_bot, get_bot
from .services.scheduler import start_scheduler, get_scheduler
from .__version__ import VERSION

logger = logging.getLogger(__name__)


def build_geo_router(db, config) -> APIRouter:
    """Build the geo intel router"""
    
    router = APIRouter(prefix="/api/geo", tags=["geo-intel"])
    
    # ==================== Health & Version ====================
    
    @router.get("/health")
    async def geo_health():
        """Geo module health check"""
        return {
            "ok": True,
            "module": "geo-intel",
            "version": VERSION,
            "config": {
                "defaultCity": config.default_city,
                "schedulerEnabled": config.enable_scheduler
            }
        }
    
    @router.get("/version")
    async def geo_version():
        """Get module version"""
        return {"version": VERSION, "frozen": False}
    
    # ==================== Map & Visualization ====================
    
    @router.get("/map")
    async def map_points(
        days: int = Query(7, ge=1, le=90),
        type: Optional[str] = Query(None, description="Event type filter"),
        limit: int = Query(500, ge=1, le=2000)
    ):
        """Get geo events as map points"""
        return await get_map_points(db, days=days, event_type=type, limit=limit)
    
    @router.get("/heatmap")
    async def heatmap_data(days: int = Query(7, ge=1, le=90)):
        """Get heatmap density data"""
        return await get_heatmap_data(db, days=days)
    
    @router.get("/top")
    async def top_places(
        days: int = Query(30, ge=1, le=90),
        limit: int = Query(50, ge=1, le=200)
    ):
        """Get top places by mention frequency"""
        return await get_top_places(db, days=days, limit=limit)
    
    @router.get("/event-types")
    async def event_types(days: int = Query(30, ge=1, le=90)):
        """Get event type distribution"""
        return await get_event_types_stats(db, days=days)
    
    # ==================== Proximity/Radar ====================
    
    @router.get("/radar")
    async def radar_nearby(
        lat: float = Query(..., description="Latitude"),
        lng: float = Query(..., description="Longitude"),
        radius: int = Query(500, ge=100, le=5000, description="Radius in meters"),
        days: int = Query(7, ge=1, le=30)
    ):
        """Get events near a location (radar mode)"""
        return await get_nearby_events(db, lat=lat, lng=lng, radius_m=radius, days=days)
    
    @router.get("/radar/alert")
    async def radar_alert_check(
        lat: float = Query(...),
        lng: float = Query(...),
        radius: int = Query(500, ge=100, le=5000),
        hours: int = Query(1, ge=1, le=24)
    ):
        """Check if radar should alert (events in last N hours)"""
        return await evaluate_radar_alert(db, lat=lat, lng=lng, radius_m=radius, hours=hours)
    
    # ==================== Summary ====================
    
    @router.get("/summary")
    async def summary(
        days: int = Query(7, ge=1, le=90),
        use_llm: bool = Query(True, description="Use LLM for summary generation")
    ):
        """Get AI-generated summary of geo activity"""
        return await generate_summary(db, days=days, use_llm=use_llm)
    
    # ==================== Radar Channels Management ====================
    
    @router.get("/channels")
    async def list_radar_channels(
        enabled_only: bool = Query(False)
    ):
        """List channels in radar watchlist"""
        query = {"enabled": True} if enabled_only else {}
        channels = await db.tg_radar_channels.find(query, {"_id": 0}).to_list(100)
        return {"ok": True, "items": channels, "total": len(channels)}
    
    @router.post("/channels")
    async def add_radar_channel(request: Request):
        """Add channel to radar watchlist"""
        body = await request.json()
        username = body.get("username", "").lower().replace("@", "").strip()
        
        if not username:
            raise HTTPException(status_code=400, detail="username required")
        
        # Check if channel exists in tg_channel_states
        channel_info = await db.tg_channel_states.find_one({"username": username})
        
        doc = {
            "username": username,
            "title": channel_info.get("title", username) if channel_info else username,
            "avatarUrl": channel_info.get("avatarUrl") if channel_info else None,
            "members": channel_info.get("participantsCount", 0) if channel_info else 0,
            "addedAt": datetime.now(timezone.utc),
            "lastScanAt": None,
            "eventsCount": 0,
            "enabled": True
        }
        
        try:
            await db.tg_radar_channels.update_one(
                {"username": username},
                {"$setOnInsert": doc},
                upsert=True
            )
            return {"ok": True, "channel": doc}
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.delete("/channels/{username}")
    async def remove_radar_channel(username: str):
        """Remove channel from radar watchlist"""
        clean = username.lower().replace("@", "").strip()
        result = await db.tg_radar_channels.delete_one({"username": clean})
        return {"ok": True, "deleted": result.deleted_count > 0}
    
    @router.patch("/channels/{username}")
    async def update_radar_channel(username: str, request: Request):
        """Update channel settings (enable/disable)"""
        body = await request.json()
        clean = username.lower().replace("@", "").strip()
        
        update = {}
        if "enabled" in body:
            update["enabled"] = bool(body["enabled"])
        
        if update:
            await db.tg_radar_channels.update_one(
                {"username": clean},
                {"$set": update}
            )
        
        return {"ok": True, "username": clean}
    
    # ==================== Search ====================
    
    @router.get("/search/channels")
    async def search_channels(
        q: str = Query(..., min_length=2, description="Search query")
    ):
        """Search Telegram channels (from existing tg_channel_states)"""
        query = {
            "$or": [
                {"username": {"$regex": q, "$options": "i"}},
                {"title": {"$regex": q, "$options": "i"}}
            ]
        }
        
        channels = await db.tg_channel_states.find(
            query,
            {"_id": 0, "username": 1, "title": 1, "avatarUrl": 1, "participantsCount": 1}
        ).limit(20).to_list(20)
        
        # Check which are already in radar
        radar_usernames = set()
        radar_channels = await db.tg_radar_channels.find({}, {"username": 1}).to_list(100)
        for rc in radar_channels:
            radar_usernames.add(rc["username"])
        
        for ch in channels:
            ch["inRadar"] = ch["username"] in radar_usernames
        
        return {"ok": True, "items": channels, "total": len(channels)}
    
    # ==================== Admin/Build ====================
    
    @router.post("/admin/rebuild")
    async def admin_rebuild(
        days: int = Query(7, ge=1, le=30)
    ):
        """Rebuild geo events for all enabled radar channels"""
        result = await rebuild_all_channels(db, days=days)
        return {"ok": True, **result}
    
    @router.post("/admin/rebuild/{username}")
    async def admin_rebuild_channel(
        username: str,
        days: int = Query(7, ge=1, le=30)
    ):
        """Rebuild geo events for a specific channel"""
        clean = username.lower().replace("@", "").strip()
        result = await build_geo_events_for_channel(db, username=clean, days=days)
        return {"ok": True, **result}
    
    @router.post("/admin/seed")
    async def admin_seed_data(
        count: int = Query(200, ge=10, le=500)
    ):
        """Seed test geo events for development"""
        from .dev_seed import seed_geo_events
        result = await seed_geo_events(db, count=count)
        return {"ok": True, **result}
    
    @router.delete("/admin/seed")
    async def admin_clear_seed():
        """Clear seeded test data"""
        from .dev_seed import clear_seed_data
        result = await clear_seed_data(db)
        return {"ok": True, **result}
    
    # ==================== Stats ====================
    
    @router.get("/stats")
    async def geo_stats(days: int = Query(30)):
        """Get overall geo module statistics"""
        from datetime import timedelta
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        total_events = await db.tg_geo_events.count_documents({"createdAt": {"$gte": since}})
        total_channels = await db.tg_radar_channels.count_documents({})
        enabled_channels = await db.tg_radar_channels.count_documents({"enabled": True})
        
        # Get event types distribution
        event_types = await get_event_types_stats(db, days=days)
        
        # Recent activity (events per day)
        pipeline = [
            {"$match": {"createdAt": {"$gte": since}}},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$createdAt"}},
                "count": {"$sum": 1}
            }},
            {"$sort": {"_id": -1}},
            {"$limit": 7}
        ]
        daily_activity = []
        async for doc in db.tg_geo_events.aggregate(pipeline):
            daily_activity.append({"date": doc["_id"], "count": doc["count"]})
        
        return {
            "ok": True,
            "totalEvents": total_events,
            "totalChannels": total_channels,
            "enabledChannels": enabled_channels,
            "eventTypes": event_types.get("items", []),
            "dailyActivity": daily_activity,
            "days": days
        }
    
    # ==================== Extended Stats ====================
    
    @router.get("/stats/places")
    async def stats_places(days: int = Query(30), limit: int = Query(20)):
        """Get top places statistics"""
        return await get_place_stats(db, days=days, limit=limit)
    
    @router.get("/stats/hourly")
    async def stats_hourly(days: int = Query(7)):
        """Get hourly activity distribution"""
        return await get_hourly_stats(db, days=days)
    
    @router.get("/stats/weekday")
    async def stats_weekday(days: int = Query(30)):
        """Get weekday activity distribution"""
        return await get_weekday_stats(db, days=days)
    
    @router.get("/stats/full")
    async def stats_full(days: int = Query(30)):
        """Get full statistics dashboard data"""
        return await get_full_stats(db, days=days)
    
    # ==================== Predictions ====================
    
    @router.get("/predict")
    async def predict(days: int = Query(30), limit: int = Query(10)):
        """Get predicted hotspots based on historical data"""
        return await predict_hotspots(db, days=days, limit=limit)
    
    @router.get("/predict/{title}")
    async def predict_place(title: str):
        """Get prediction for specific place"""
        return await get_place_prediction(db, title=title)
    
    # ==================== Alert Subscriptions ====================
    
    @router.post("/alerts/subscribe")
    async def subscribe_alert(request: Request):
        """Subscribe to proximity alerts"""
        body = await request.json()
        
        actor_id = body.get("actorId")
        chat_id = body.get("telegramChatId")
        lat = body.get("lat")
        lng = body.get("lng")
        radius = body.get("radius", 1000)
        event_types = body.get("eventTypes")
        
        if not actor_id or not chat_id:
            raise HTTPException(status_code=400, detail="actorId and telegramChatId required")
        
        if lat is None or lng is None:
            raise HTTPException(status_code=400, detail="lat and lng required")
        
        return await create_subscription(
            db, 
            actor_id=actor_id,
            telegram_chat_id=int(chat_id),
            lat=float(lat),
            lng=float(lng),
            radius=int(radius),
            event_types=event_types
        )
    
    @router.post("/alerts/location")
    async def update_alert_location(request: Request):
        """Update user location for alerts"""
        body = await request.json()
        actor_id = body.get("actorId")
        lat = body.get("lat")
        lng = body.get("lng")
        
        if not actor_id or lat is None or lng is None:
            raise HTTPException(status_code=400, detail="actorId, lat, lng required")
        
        return await update_location(db, actor_id, float(lat), float(lng))
    
    @router.delete("/alerts/subscribe/{actor_id}")
    async def unsubscribe_alert(actor_id: str):
        """Unsubscribe from alerts"""
        return await unsubscribe(db, actor_id)
    
    @router.get("/alerts/subscription/{actor_id}")
    async def get_alert_subscription(actor_id: str):
        """Get subscription status"""
        sub = await get_subscription(db, actor_id)
        if not sub:
            return {"ok": True, "subscribed": False}
        return {"ok": True, "subscribed": True, "subscription": sub}
    
    @router.post("/alerts/test")
    async def test_alert(request: Request):
        """Send test alert to verify bot connection"""
        body = await request.json()
        chat_id = body.get("telegramChatId")
        
        if not chat_id:
            raise HTTPException(status_code=400, detail="telegramChatId required")
        
        return await send_test_alert(int(chat_id))
    
    # ==================== Probability Engine ====================
    
    @router.get("/probability")
    async def get_probabilities(limit: int = Query(20)):
        """Get places with highest event probability"""
        from .services.probability_repository import ProbabilityRepository
        repo = ProbabilityRepository(db)
        items = await repo.get_top_probabilities(limit=limit)
        return {"ok": True, "items": items}
    
    @router.post("/probability/rebuild")
    async def rebuild_probabilities():
        """Manually trigger probability recalculation"""
        from .services.probability_repository import ProbabilityRepository
        from .services.probability_engine import ProbabilityEngine
        repo = ProbabilityRepository(db)
        engine = ProbabilityEngine(repo)
        result = await engine.rebuild()
        return result
    
    # ==================== Fused Events ====================
    
    @router.get("/fused")
    async def get_fused_events():
        """Get active fused events (combined from multiple sources)"""
        from .services.fusion_repository import FusionRepository
        repo = FusionRepository(db)
        items = await repo.get_active_fused_events()
        return {"ok": True, "count": len(items), "items": items}
    
    @router.post("/fused/rebuild")
    async def rebuild_fused():
        """Manually trigger fusion recalculation"""
        from .services.fusion_repository import FusionRepository
        from .services.fusion_engine import FusionEngine
        repo = FusionRepository(db)
        engine = FusionEngine(repo)
        result = await engine.rebuild()
        return result
    
    # ==================== Signal Decay ====================
    
    @router.post("/decay/run")
    async def run_decay():
        """Manually trigger decay processing"""
        from .services.signal_decay import DecayWorker
        worker = DecayWorker(db)
        result = await worker.run_once()
        return result
    
    # ==================== Event Types Config ====================
    
    @router.get("/config/event-types")
    async def get_event_types():
        """Get event types configuration"""
        from .config.event_types import EVENT_TYPES
        return {"ok": True, "types": EVENT_TYPES}
    
    # ==================== Playback ====================
    
    @router.get("/playback")
    async def get_playback(
        hours: int = Query(24, ge=1, le=168),
        step: int = Query(30, ge=5, le=120)
    ):
        """Get activity playback frames for timeline replay"""
        from .services.playback import build_playback_frames
        return await build_playback_frames(db, hours=hours, step_minutes=step)
    
    @router.get("/playback/summary")
    async def get_playback_summary(hours: int = Query(24)):
        """Get summary statistics for playback period"""
        from .services.playback import get_playback_summary as playback_summary
        return await playback_summary(db, hours=hours)
    
    # ==================== Risk Map ====================
    
    @router.get("/risk")
    async def get_risk_map(
        days: int = Query(7, ge=1, le=30),
        precision: int = Query(3, ge=2, le=4)
    ):
        """Get risk map with severity-weighted zones"""
        from .services.risk_map import build_risk_map
        return await build_risk_map(db, days=days, grid_precision=precision)
    
    @router.get("/risk/location")
    async def get_location_risk(
        lat: float = Query(...),
        lng: float = Query(...),
        radius: int = Query(500),
        days: int = Query(7)
    ):
        """Get risk score for specific location"""
        from .services.risk_map import get_risk_at_location
        return await get_risk_at_location(db, lat=lat, lng=lng, radius_m=radius, days=days)
    
    # ==================== Route Safety ====================
    
    @router.post("/route/check")
    async def check_route(request: Request):
        """Check route for safety hazards"""
        from .services.route_safety import check_route_safety
        body = await request.json()
        route_points = body.get("points", [])
        days = body.get("days", 3)
        return await check_route_safety(db, route_points=route_points, days=days)
    
    @router.post("/route/avoidance")
    async def get_route_avoidance(request: Request):
        """Get zones to avoid between two points"""
        from .services.route_safety import suggest_avoidance
        body = await request.json()
        start = body.get("start", {})
        end = body.get("end", {})
        days = body.get("days", 3)
        return await suggest_avoidance(db, start=start, end=end, days=days)
    
    @router.get("/route/direction")
    async def get_safe_direction(
        lat: float = Query(...),
        lng: float = Query(...),
        radius: int = Query(1000),
        days: int = Query(3)
    ):
        """Get safest direction to move from location"""
        from .services.route_safety import get_safest_direction
        return await get_safest_direction(db, lat=lat, lng=lng, radius_m=radius, days=days)
    
    # ==================== Dynamic Risk Zones ====================
    
    @router.get("/risk/zones")
    async def get_risk_zones():
        """Get active dynamic risk zones"""
        from .services.risk_zone_repository import RiskZoneRepository
        repo = RiskZoneRepository(db)
        items = await repo.get_active_zones()
        return {"ok": True, "count": len(items), "items": items}
    
    @router.get("/risk/zones/near")
    async def get_zones_near(
        lat: float = Query(...),
        lng: float = Query(...),
        radius: int = Query(1000, ge=100, le=5000)
    ):
        """Get risk zones near a location"""
        from .services.risk_zone_repository import RiskZoneRepository
        repo = RiskZoneRepository(db)
        items = await repo.get_zones_near_location(lat=lat, lng=lng, radius_m=radius)
        return {"ok": True, "count": len(items), "items": items}
    
    @router.post("/risk/zones/rebuild")
    async def rebuild_risk_zones():
        """Manually trigger risk zone rebuilding"""
        from .services.risk_zone_repository import RiskZoneRepository
        from .services.risk_zone_engine import RiskZoneEngine
        repo = RiskZoneRepository(db)
        engine = RiskZoneEngine(repo)
        result = await engine.rebuild()
        return result
    
    # ==================== Movement Tracking ====================
    
    @router.get("/movements")
    async def get_movements():
        """Get active movement trajectories"""
        from .services.movement_repository import MovementRepository
        repo = MovementRepository(db)
        items = await repo.get_active_movements()
        return {"ok": True, "count": len(items), "items": items}
    
    @router.get("/movements/near")
    async def get_movements_near(
        lat: float = Query(...),
        lng: float = Query(...),
        radius: int = Query(1000, ge=100, le=5000)
    ):
        """Get movements passing near a location"""
        from .services.movement_repository import MovementRepository
        repo = MovementRepository(db)
        items = await repo.get_movements_near_location(lat=lat, lng=lng, radius_m=radius)
        return {"ok": True, "count": len(items), "items": items}
    
    @router.post("/movements/rebuild")
    async def rebuild_movements():
        """Manually trigger movement detection"""
        from .services.movement_repository import MovementRepository
        from .services.movement_engine import MovementEngine
        repo = MovementRepository(db)
        engine = MovementEngine(repo)
        result = await engine.rebuild()
        return result
    
    # ==================== Bot API ====================
    
    @router.post("/bot/webhook")
    async def bot_webhook(request: Request):
        """Telegram webhook endpoint for bot updates"""
        from .services.bot_command_router import BotCommandRouter
        
        # Define send_message function (placeholder - needs actual bot token)
        async def send_message(chat_id: int, text: str, reply_markup=None, parse_mode=None):
            import httpx
            bot_token = os.environ.get("TG_BOT_TOKEN") or os.environ.get("GEO_BOT_TOKEN", "")
            if not bot_token:
                logger.warning("TG_BOT_TOKEN not set")
                return {"ok": False, "error": "no_token"}
            
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": text}
            if reply_markup:
                payload["reply_markup"] = json.dumps(reply_markup)
            if parse_mode:
                payload["parse_mode"] = parse_mode
            
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                return resp.json()
        
        router_instance = BotCommandRouter(db, send_message)
        
        body = await request.json()
        result = await router_instance.handle_update(body)
        
        return {"ok": True, "result": result}
    
    @router.get("/bot/users")
    async def bot_users():
        """Get bot users statistics"""
        from .services.bot_user_service import BotUserService
        service = BotUserService(db)
        stats = await service.get_users_count()
        return {"ok": True, **stats}
    
    @router.get("/bot/user/{actor_id}")
    async def bot_user_info(actor_id: str):
        """Get bot user info"""
        from .services.bot_user_service import BotUserService
        from .services.bot_settings_service import BotSettingsService
        from .services.bot_location_service import BotLocationService
        
        user_service = BotUserService(db)
        settings_service = BotSettingsService(db)
        location_service = BotLocationService(db)
        
        user = await user_service.get_user(actor_id)
        settings = await settings_service.get_settings(actor_id)
        location = await location_service.get_location(actor_id)
        
        return {
            "ok": True,
            "user": user,
            "settings": settings,
            "location": location
        }
    
    @router.post("/bot/alerts/check")
    async def bot_check_alerts():
        """Manually trigger proximity check for all users"""
        from .services.bot_alert_scheduler import BotAlertScheduler
        
        # Create scheduler without send_message (dry run)
        scheduler = BotAlertScheduler(db, send_message_func=None)
        result = await scheduler.run_once()
        return result
    
    @router.post("/bot/send/{chat_id}")
    async def bot_send_message(chat_id: int, request: Request):
        """Send message to user (for testing)"""
        import httpx
        
        body = await request.json()
        text = body.get("text", "Test message")
        
        bot_token = os.environ.get("TG_BOT_TOKEN") or os.environ.get("GEO_BOT_TOKEN", "")
        if not bot_token:
            return {"ok": False, "error": "TG_BOT_TOKEN not set"}
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": body.get("parse_mode", "Markdown")
        }
        
        if body.get("reply_markup"):
            payload["reply_markup"] = json.dumps(body["reply_markup"])
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload)
            return resp.json()
    
    @router.get("/bot/settings")
    async def bot_settings_defaults():
        """Get default bot settings"""
        from .services.bot_settings_service import (
            DEFAULT_SETTINGS, RADIUS_OPTIONS, SENSITIVITY_OPTIONS, EVENT_TYPES
        )
        return {
            "ok": True,
            "defaults": DEFAULT_SETTINGS,
            "radiusOptions": RADIUS_OPTIONS,
            "sensitivityOptions": SENSITIVITY_OPTIONS,
            "eventTypes": EVENT_TYPES
        }
    
    # ==================== User Reports (Crowd Intelligence) ====================
    
    @router.post("/report")
    async def create_report(request: Request):
        """Create user report (crowd signal)"""
        from .services.report_ingestion import create_user_report
        
        body = await request.json()
        actor_id = body.get("actorId") or body.get("actor_id")
        event_type = body.get("eventType") or body.get("type", "other")
        lat = body.get("lat")
        lng = body.get("lng")
        
        if not actor_id or lat is None or lng is None:
            raise HTTPException(status_code=400, detail="actorId, lat, lng required")
        
        result = await create_user_report(
            db,
            actor_id=actor_id,
            event_type=event_type,
            lat=lat,
            lng=lng,
            username=body.get("username"),
            photo_url=body.get("photoUrl"),
            description=body.get("description"),
            address_text=body.get("addressText")
        )
        
        return result
    
    @router.post("/report/{report_id}/confirm")
    async def confirm_report(report_id: str, request: Request):
        """Confirm or reject a report"""
        from .services.report_ingestion import process_confirmation
        
        body = await request.json()
        actor_id = body.get("actorId") or body.get("actor_id")
        action = body.get("action", "confirm")  # confirm | reject | false
        
        if not actor_id:
            raise HTTPException(status_code=400, detail="actorId required")
        
        result = await process_confirmation(db, report_id, actor_id, action)
        return result
    
    @router.get("/reports")
    async def list_reports(
        status: Optional[str] = Query(None, description="Filter by status"),
        event_type: Optional[str] = Query(None, description="Filter by event type"),
        limit: int = Query(50, ge=1, le=200)
    ):
        """List user reports"""
        query = {}
        if status:
            query["status"] = status
        if event_type:
            query["eventType"] = event_type
        
        reports = await db.geo_user_reports.find(
            query,
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": reports, "total": len(reports)}
    
    @router.get("/reports/user/{actor_id}")
    async def user_reports(actor_id: str, limit: int = Query(20)):
        """Get reports by user"""
        reports = await db.geo_user_reports.find(
            {"actorId": actor_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": reports, "total": len(reports)}
    
    @router.get("/reports/user/{actor_id}/stats")
    async def user_stats(actor_id: str):
        """Get user report statistics"""
        from .services.report_ingestion import get_user_stats
        return await get_user_stats(db, actor_id)
    
    @router.get("/leaderboard")
    async def leaderboard(limit: int = Query(10, ge=1, le=50)):
        """Get reporter leaderboard"""
        from .services.report_ingestion import get_leaderboard
        leaders = await get_leaderboard(db, limit)
        return {"ok": True, "items": leaders}
    
    @router.get("/report-types")
    async def report_types():
        """Get available report types"""
        from .services.report_ingestion import EVENT_TYPES
        types = [
            {"type": k, **v} for k, v in EVENT_TYPES.items()
        ]
        return {"ok": True, "types": types}
    
    # ==================== Location Picker for Telegram WebApp ====================
    
    @router.post("/location-picker/set")
    async def set_picker_location(request: Request):
        """Set location from map picker WebApp"""
        from .services.map_location_picker import MapLocationPickerService
        
        try:
            data = await request.json()
        except:
            raise HTTPException(400, "Invalid JSON")
        
        token = data.get("token")
        lat = data.get("lat")
        lng = data.get("lng")
        address = data.get("address")
        
        if not token:
            raise HTTPException(400, "Token required")
        if lat is None or lng is None:
            raise HTTPException(400, "Coordinates required")
        
        picker_svc = MapLocationPickerService(db)
        result = await picker_svc.set_location(token, lat, lng, address)
        
        return result
    
    @router.get("/location-picker/status/{token}")
    async def get_picker_status(token: str):
        """Check location picker token status"""
        from .services.map_location_picker import MapLocationPickerService
        
        picker_svc = MapLocationPickerService(db)
        result = await picker_svc.get_token_location(token)
        
        return result
    
    # ==================== User Tier & Trust ====================
    
    @router.get("/user/tier/{actor_id}")
    async def get_user_tier(actor_id: str):
        """Get user's subscription tier and limits"""
        from .services.user_tier_service import UserTierService
        
        tier_svc = UserTierService(db)
        return await tier_svc.get_user_tier(actor_id)
    
    @router.get("/user/trust/{actor_id}")
    async def get_user_trust(actor_id: str):
        """Get user's trust score"""
        from .services.trust_score_service import TrustScoreService
        
        trust_svc = TrustScoreService(db)
        return await trust_svc.get_trust_score(actor_id)
    
    @router.get("/trust/leaderboard")
    async def trust_leaderboard(limit: int = Query(10, ge=1, le=50)):
        """Get top users by trust score"""
        from .services.trust_score_service import TrustScoreService
        
        trust_svc = TrustScoreService(db)
        leaders = await trust_svc.get_leaderboard(limit)
        return {"ok": True, "items": leaders}
    
    # ==================== Admin Moderation ====================
    
    @router.get("/admin/moderation/pending")
    async def get_pending_moderation(
        limit: int = Query(20, ge=1, le=100),
        admin_key: str = Query(None)
    ):
        """Get pending signals for moderation"""
        from .services.admin_moderation_service import AdminModerationService
        
        # Simple admin key check
        expected_key = os.environ.get("ADMIN_ACCESS_KEY", "")
        if admin_key != expected_key:
            raise HTTPException(403, "Admin access required")
        
        mod_svc = AdminModerationService(db)
        pending = await mod_svc.get_pending_signals(limit)
        count = await mod_svc.get_pending_count()
        
        return {"ok": True, "items": pending, "total": count}
    
    @router.post("/admin/moderation/approve/{signal_id}")
    async def approve_signal(
        signal_id: str,
        admin_key: str = Query(None)
    ):
        """Approve a pending signal (admin only)"""
        from .services.admin_moderation_service import AdminModerationService
        
        expected_key = os.environ.get("ADMIN_ACCESS_KEY", "")
        if admin_key != expected_key:
            raise HTTPException(403, "Admin access required")
        
        mod_svc = AdminModerationService(db)
        result = await mod_svc.approve_signal(signal_id, admin_id=0)
        
        return result
    
    @router.post("/admin/moderation/reject/{signal_id}")
    async def reject_signal(
        signal_id: str,
        reason: str = Query(None),
        admin_key: str = Query(None)
    ):
        """Reject a pending signal (admin only)"""
        from .services.admin_moderation_service import AdminModerationService
        
        expected_key = os.environ.get("ADMIN_ACCESS_KEY", "")
        if admin_key != expected_key:
            raise HTTPException(403, "Admin access required")
        
        mod_svc = AdminModerationService(db)
        result = await mod_svc.reject_signal(signal_id, admin_id=0, reason=reason)
        
        return result
    
    # ==================== AI Signal Classification ====================
    
    @router.post("/classify")
    async def classify_text(request: Request):
        """Classify text message to signal type using AI"""
        from .services.ai_signal_classifier import AISignalClassifier
        
        try:
            data = await request.json()
        except:
            raise HTTPException(400, "Invalid JSON")
        
        text = data.get("text", "")
        
        classifier = AISignalClassifier(db)
        result = await classifier.classify_text(text)
        
        return {"ok": True, **result}
    
    # ==================== Rewards System ====================
    
    @router.get("/rewards/balance/{actor_id}")
    async def get_rewards_balance(actor_id: str):
        """Get user's rewards balance"""
        from .services.rewards_service import RewardsService
        
        rewards_svc = RewardsService(db)
        return await rewards_svc.get_balance(actor_id)
    
    @router.post("/rewards/confirm/{signal_id}")
    async def confirm_signal(signal_id: str, request: Request):
        """Confirm a signal (user sees it too) - rewards both parties"""
        from .services.rewards_service import RewardsService
        
        try:
            data = await request.json()
        except:
            data = {}
        
        actor_id = data.get("actorId")
        if not actor_id:
            raise HTTPException(400, "actorId required")
        
        # Get signal creator
        signal = await db.tg_crowd_signals.find_one({"_id": signal_id})
        creator_id = signal.get("actorId") if signal else None
        
        rewards_svc = RewardsService(db)
        result = await rewards_svc.reward_confirmation(actor_id, signal_id, creator_id)
        
        return result
    
    @router.get("/rewards/signal/{signal_id}")
    async def get_signal_confirmations(signal_id: str):
        """Get signal confirmation count and strength"""
        from .services.rewards_service import RewardsService
        
        rewards_svc = RewardsService(db)
        return await rewards_svc.get_signal_confirmations(signal_id)
    
    @router.post("/rewards/withdraw/{actor_id}")
    async def withdraw_rewards(actor_id: str, method: str = Query("stars")):
        """Request withdrawal of rewards"""
        from .services.rewards_service import RewardsService
        
        rewards_svc = RewardsService(db)
        return await rewards_svc.withdraw(actor_id, method)
    
    @router.get("/rewards/history/{actor_id}")
    async def get_reward_history(actor_id: str, limit: int = Query(20, ge=1, le=100)):
        """Get user's reward transaction history"""
        from .services.rewards_service import RewardsService
        
        rewards_svc = RewardsService(db)
        history = await rewards_svc.get_transaction_history(actor_id, limit)
        return {"ok": True, "items": history}
    
    @router.get("/rewards/leaderboard")
    async def rewards_leaderboard(limit: int = Query(10, ge=1, le=50)):
        """Get top earners leaderboard"""
        from .services.rewards_service import RewardsService
        
        rewards_svc = RewardsService(db)
        leaders = await rewards_svc.get_top_earners(limit)
        return {"ok": True, "items": leaders}
    
    # ==================== Mini App Endpoints ====================
    
    @router.post("/miniapp/report")
    async def miniapp_report_signal(request: Request):
        """Report a new signal from Mini App"""
        import uuid
        from .services.channel_publisher import get_channel_publisher
        
        body = await request.json()
        
        signal_type = body.get("type")
        lat = body.get("lat")
        lng = body.get("lng")
        description = body.get("description", "")
        source = body.get("source", "miniapp")
        user_id = body.get("userId")
        username = body.get("username")
        
        if not signal_type or lat is None or lng is None:
            raise HTTPException(status_code=400, detail="type, lat, lng required")
        
        # Create signal document
        signal_doc = {
            "id": str(uuid.uuid4()),
            "type": signal_type,
            "lat": float(lat),
            "lng": float(lng),
            "location": {"type": "Point", "coordinates": [float(lng), float(lat)]},
            "description": description,
            "source": source,
            "userId": user_id,
            "username": username,
            "confidence": 0.5,  # Initial confidence
            "confirmations": 0,
            "rejections": 0,
            "status": "active",
            "createdAt": datetime.now(timezone.utc),
            "expiresAt": datetime.now(timezone.utc) + timedelta(hours=1),
            "publishedToChannel": False,
        }
        
        await db.tg_miniapp_signals.insert_one(signal_doc)
        
        # Publish to Telegram channel
        publisher = get_channel_publisher()
        channel_result = None
        if publisher:
            channel_result = await publisher.publish_signal(signal_doc)
            if channel_result.get("ok"):
                await db.tg_miniapp_signals.update_one(
                    {"id": signal_doc["id"]},
                    {"$set": {
                        "publishedToChannel": True,
                        "channelMessageId": channel_result.get("message_id")
                    }}
                )
        
        # Return without _id
        signal_doc.pop("_id", None)
        
        return {
            "ok": True, 
            "signal": signal_doc,
            "channelPublished": channel_result.get("ok") if channel_result else False
        }
    
    @router.post("/miniapp/report-with-photo")
    async def miniapp_report_with_photo(
        type: str = Form(...),
        lat: float = Form(...),
        lng: float = Form(...),
        description: str = Form(""),
        userId: str = Form("anonymous"),
        username: str = Form(""),
        photo: Optional[UploadFile] = File(None)
    ):
        """
        Report a new signal with optional photo upload.
        Publishes to Telegram channel with photo if provided.
        """
        from .services.channel_publisher import get_channel_publisher
        import httpx
        
        signal_id = str(uuid.uuid4())
        
        # Get user privacy settings
        user_settings = await db.tg_miniapp_users.find_one({"telegramId": userId})
        location_retention = user_settings.get("locationRetention", "1h") if user_settings else "1h"
        location_precision = user_settings.get("locationPrecision", "exact") if user_settings else "exact"
        
        # Apply location fuzzing if approximate
        actual_lat = lat
        actual_lng = lng
        if location_precision == "approx":
            import random
            actual_lat += random.uniform(-0.0008, 0.0008)  # ~100m
            actual_lng += random.uniform(-0.0008, 0.0008)
        
        # Calculate expiration based on retention
        retention_minutes = {
            "none": 5,
            "15m": 15,
            "1h": 60,
            "24h": 1440
        }
        expires_minutes = retention_minutes.get(location_retention, 60)
        
        # Process photo if provided
        photo_url = None
        photo_data = None
        if photo and photo.filename:
            try:
                photo_bytes = await photo.read()
                photo_data = base64.b64encode(photo_bytes).decode('utf-8')
                # Store photo in DB as base64 (for demo; in production use S3/Cloudinary)
                photo_url = f"data:image/jpeg;base64,{photo_data[:100]}..."  # Truncated for response
            except Exception as e:
                logger.error(f"Photo processing error: {e}")
        
        # Create signal document
        signal_doc = {
            "id": signal_id,
            "type": type,
            "lat": float(actual_lat),
            "lng": float(actual_lng),
            "location": {"type": "Point", "coordinates": [float(actual_lng), float(actual_lat)]},
            "description": description,
            "source": "miniapp",
            "userId": userId,
            "username": username,
            "hasPhoto": photo_data is not None,
            "photoBase64": photo_data,  # Store full base64
            "confidence": 0.6 if photo_data else 0.5,  # Higher confidence with photo
            "confirmations": 0,
            "rejections": 0,
            "status": "active",
            "createdAt": datetime.now(timezone.utc),
            "expiresAt": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
            "publishedToChannel": False,
        }
        
        await db.tg_miniapp_signals.insert_one(signal_doc)
        
        # Publish to Telegram channel
        publisher = get_channel_publisher()
        channel_result = {"ok": False}
        
        if publisher:
            bot_token = os.environ.get("BOT_TOKEN")
            channel_id = os.environ.get("CHANNEL_ID", "@ARKHOR")
            
            if photo_data and bot_token:
                # Send photo with caption to channel
                try:
                    message = publisher.format_alert_post(signal_doc)
                    photo_bytes = base64.b64decode(photo_data)
                    
                    async with httpx.AsyncClient() as client:
                        files = {"photo": ("signal.jpg", photo_bytes, "image/jpeg")}
                        data = {
                            "chat_id": channel_id,
                            "caption": message,
                            "parse_mode": "HTML"
                        }
                        response = await client.post(
                            f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                            data=data,
                            files=files,
                            timeout=30.0
                        )
                        result = response.json()
                        if result.get("ok"):
                            channel_result = {"ok": True, "message_id": result["result"]["message_id"]}
                            logger.info(f"Published signal with photo to channel")
                        else:
                            logger.error(f"Channel photo publish failed: {result}")
                            # Fallback to text-only
                            channel_result = await publisher.publish_signal(signal_doc)
                except Exception as e:
                    logger.error(f"Photo publish error: {e}")
                    channel_result = await publisher.publish_signal(signal_doc)
            else:
                # Text-only publish
                channel_result = await publisher.publish_signal(signal_doc)
            
            if channel_result.get("ok"):
                await db.tg_miniapp_signals.update_one(
                    {"id": signal_id},
                    {"$set": {
                        "publishedToChannel": True,
                        "channelMessageId": channel_result.get("message_id")
                    }}
                )
        
        # Update user stats
        await db.tg_miniapp_users.update_one(
            {"telegramId": userId},
            {
                "$inc": {"signalsSent": 1, "xp": 10},
                "$set": {"lastSignalAt": datetime.now(timezone.utc)}
            },
            upsert=True
        )
        
        # Return response (without large photo data)
        response_doc = {k: v for k, v in signal_doc.items() if k != "photoBase64"}
        response_doc.pop("_id", None)
        
        return {
            "ok": True,
            "signal": response_doc,
            "channelPublished": channel_result.get("ok"),
            "xpEarned": 10
        }
    
    @router.post("/miniapp/signal/{signal_id}/vote")
    async def miniapp_vote_signal(signal_id: str, request: Request):
        """Vote on a signal (confirm/reject)"""
        body = await request.json()
        
        vote = body.get("vote")  # 'confirm' or 'reject'
        user_id = body.get("userId")
        
        if vote not in ["confirm", "reject"]:
            raise HTTPException(status_code=400, detail="vote must be 'confirm' or 'reject'")
        
        # Find signal
        signal = await db.tg_miniapp_signals.find_one({"id": signal_id})
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Check if user already voted
        existing_vote = await db.tg_miniapp_votes.find_one({
            "signalId": signal_id,
            "userId": user_id
        })
        
        if existing_vote:
            return {"ok": False, "error": "Already voted"}
        
        # Record vote
        vote_doc = {
            "signalId": signal_id,
            "userId": user_id,
            "vote": vote,
            "createdAt": datetime.now(timezone.utc)
        }
        await db.tg_miniapp_votes.insert_one(vote_doc)
        
        # Update signal confidence
        update_field = "confirmations" if vote == "confirm" else "rejections"
        await db.tg_miniapp_signals.update_one(
            {"id": signal_id},
            {"$inc": {update_field: 1}}
        )
        
        # Recalculate confidence
        signal = await db.tg_miniapp_signals.find_one({"id": signal_id})
        total_votes = signal.get("confirmations", 0) + signal.get("rejections", 0)
        if total_votes > 0:
            new_confidence = signal.get("confirmations", 0) / total_votes
            await db.tg_miniapp_signals.update_one(
                {"id": signal_id},
                {"$set": {"confidence": new_confidence}}
            )
        
        return {"ok": True, "vote": vote}
    
    @router.get("/miniapp/user/{user_id}/profile")
    async def miniapp_user_profile(user_id: str):
        """Get user profile for Mini App"""
        # Find or create user
        user = await db.tg_miniapp_users.find_one({"telegramId": user_id})
        
        if not user:
            # Create new user
            user = {
                "telegramId": user_id,
                "signalsSent": 0,
                "signalsConfirmed": 0,
                "trustScore": 50,
                "level": 1,
                "xp": 0,
                "xpNext": 100,
                "createdAt": datetime.now(timezone.utc)
            }
            await db.tg_miniapp_users.insert_one(user)
        
        # Remove _id
        user.pop("_id", None)
        
        return {"ok": True, "user": user}
    
    @router.get("/miniapp/user/{user_id}/settings")
    async def miniapp_get_user_settings(user_id: str):
        """Get user privacy settings"""
        user = await db.tg_miniapp_users.find_one({"telegramId": user_id})
        
        default_settings = {
            "locationRetention": "1h",
            "locationPrecision": "exact"
        }
        
        if user:
            return {
                "ok": True,
                "settings": {
                    "locationRetention": user.get("locationRetention", default_settings["locationRetention"]),
                    "locationPrecision": user.get("locationPrecision", default_settings["locationPrecision"])
                }
            }
        
        return {"ok": True, "settings": default_settings}
    
    @router.post("/miniapp/user/{user_id}/settings")
    async def miniapp_update_user_settings(user_id: str, request: Request):
        """Update user privacy settings"""
        body = await request.json()
        
        valid_retention = ["none", "15m", "1h", "24h"]
        valid_precision = ["exact", "approx"]
        
        update_data = {}
        
        if "locationRetention" in body and body["locationRetention"] in valid_retention:
            update_data["locationRetention"] = body["locationRetention"]
        
        if "locationPrecision" in body and body["locationPrecision"] in valid_precision:
            update_data["locationPrecision"] = body["locationPrecision"]
        
        if update_data:
            await db.tg_miniapp_users.update_one(
                {"telegramId": user_id},
                {"$set": update_data},
                upsert=True
            )
        
        return {"ok": True, "updated": update_data}
    
    @router.get("/miniapp/user/{user_id}/alerts")
    async def miniapp_user_alerts(user_id: str, limit: int = Query(20, ge=1, le=100)):
        """Get alerts for user"""
        # Get recent signals (for now, just return all recent signals)
        signals = await db.tg_miniapp_signals.find(
            {"status": "active"},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": signals, "unread": 0}
    
    @router.get("/miniapp/subscription/status")
    async def miniapp_subscription_status(userId: str = Query(...)):
        """Get subscription status for Mini App"""
        from .services.subscription_service import SubscriptionService
        
        actor_id = f"tg_{userId}"
        sub_svc = SubscriptionService(db)
        is_subscribed = await sub_svc.is_subscribed(actor_id)
        
        result = {
            "ok": True,
            "isSubscribed": is_subscribed,
            "plan": "pro" if is_subscribed else "free",
            "priceStars": 200,
        }
        
        if is_subscribed:
            sub = await sub_svc.get_subscription(actor_id)
            if sub:
                result["expiresAt"] = sub.get("expiresAt")
        
        return result
    
    @router.post("/miniapp/subscription/create-invoice")
    async def miniapp_create_invoice(request: Request):
        """Create Telegram Stars invoice for subscription"""
        from .services.subscription_service import PaymentService
        
        body = await request.json()
        user_id = body.get("userId")
        chat_id = body.get("chatId")
        
        if not user_id:
            raise HTTPException(status_code=400, detail="userId required")
        
        actor_id = f"tg_{user_id}"
        payment_svc = PaymentService(db)
        result = await payment_svc.create_invoice(chat_id or user_id, actor_id)
        
        return result
    
    @router.get("/miniapp/channel/check")
    async def miniapp_check_channel_subscription(
        userId: str = Query(..., description="Telegram user ID"),
        channel: str = Query(..., description="Channel username without @")
    ):
        """
        Check if user is subscribed to a Telegram channel.
        Uses Bot API getChatMember method.
        """
        import httpx
        
        bot_token = os.environ.get("BOT_TOKEN")
        if not bot_token:
            return {"ok": False, "error": "Bot token not configured", "isMember": False}
        
        try:
            # Format channel as @username
            chat_id = f"@{channel}" if not channel.startswith("@") else channel
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.telegram.org/bot{bot_token}/getChatMember",
                    params={
                        "chat_id": chat_id,
                        "user_id": userId
                    },
                    timeout=10.0
                )
                
                data = response.json()
                
                if data.get("ok"):
                    status = data.get("result", {}).get("status", "")
                    # member, administrator, creator = subscribed
                    # left, kicked, restricted = not subscribed
                    is_member = status in ["member", "administrator", "creator"]
                    return {
                        "ok": True,
                        "isMember": is_member,
                        "status": status,
                        "channel": channel
                    }
                else:
                    error_desc = data.get("description", "Unknown error")
                    # User not found in chat = not subscribed
                    if "user not found" in error_desc.lower() or "chat not found" in error_desc.lower():
                        return {"ok": True, "isMember": False, "status": "not_found", "channel": channel}
                    return {"ok": False, "error": error_desc, "isMember": False}
                    
        except Exception as e:
            logger.error(f"Channel check error: {e}")
            return {"ok": False, "error": str(e), "isMember": False}
    
    @router.get("/miniapp/channel/preview-post")
    async def preview_channel_post(
        signal_type: str = Query("police", description="Signal type"),
        description: str = Query("", description="Optional description")
    ):
        """Preview how a signal post will look in the channel"""
        from .services.channel_publisher import ChannelPublisher, SIGNAL_CONFIG, DEFAULT_CONFIG
        
        # Create mock signal
        mock_signal = {
            "type": signal_type,
            "lat": 50.4501,
            "lng": 30.5234,
            "description": description,
            "confirmations": 3,
            "createdAt": datetime.now(timezone.utc)
        }
        
        # Get formatted post
        publisher = ChannelPublisher("dummy", "@ARKHOR")
        formatted = publisher.format_alert_post(mock_signal)
        
        return {
            "ok": True,
            "signal_type": signal_type,
            "config": SIGNAL_CONFIG.get(signal_type, DEFAULT_CONFIG),
            "preview": formatted,
            "html_preview": formatted.replace("\n", "<br>")
        }
    
    return router
