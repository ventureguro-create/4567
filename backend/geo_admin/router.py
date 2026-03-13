"""
Geo Admin API Router
Complete admin panel endpoints
"""
import os
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional, List
from pydantic import BaseModel

from .auth import require_admin, create_admin_session, revoke_session, ADMIN_ACCESS_KEY
from .services.dashboard_service import get_dashboard_stats
from .services.channels_service import (
    get_channels, add_channel, update_channel, delete_channel, get_channel_stats,
    search_channel_live
)
from .services.users_service import get_users, get_user_details, get_user_analytics
from .services.bot_admin_service import (
    get_bot_status, set_webhook, delete_webhook, send_test_message,
    get_delivery_queue, retry_failed_deliveries
)
from .services.sessions_service import (
    get_sessions, add_session, remove_session, update_session_status,
    test_session, get_session_stats
)
from .services.analytics_service import (
    get_events_by_day, get_top_event_types, get_top_districts,
    get_source_breakdown, get_alert_analytics, get_channel_performance
)
from .services.logs_service import (
    get_admin_logs, get_parsing_logs, get_delivery_logs, get_error_summary,
    log_admin_action
)
from .services.signals_service import (
    get_signals, get_signal_by_id, confirm_signal, dismiss_signal,
    update_signal, create_manual_signal, delete_signal, merge_signals,
    bulk_update_status, EVENT_TYPES
)
from typing import Dict, Any

logger = logging.getLogger(__name__)


# === Request Models ===

class LoginRequest(BaseModel):
    access_key: str

class AddChannelRequest(BaseModel):
    username: str
    priority: int = 5
    tags: List[str] = []

class UpdateChannelRequest(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    tags: Optional[List[str]] = None

class WebhookRequest(BaseModel):
    url: str

class TestMessageRequest(BaseModel):
    chat_id: int
    message: Optional[str] = None

class AddSessionRequest(BaseModel):
    name: str
    session_string: str
    api_id: int
    api_hash: str
    max_threads: int = 4
    channels_limit: int = 40


# === Signals Request Models ===

class CreateSignalRequest(BaseModel):
    event_type: str
    lat: float
    lng: float
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[str] = None
    truth_score: float = 0.9

class UpdateSignalRequest(BaseModel):
    event_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: Optional[str] = None
    truth_score: Optional[float] = None

class SignalActionRequest(BaseModel):
    note: Optional[str] = None
    reason: Optional[str] = None

class MergeSignalsRequest(BaseModel):
    signal_ids: List[str]
    primary_signal_id: str

class BulkStatusRequest(BaseModel):
    signal_ids: List[str]
    status: str


def build_admin_router(db) -> APIRouter:
    """Build the geo admin router"""
    
    router = APIRouter(prefix="/api/geo-admin", tags=["geo-admin"])
    
    # ==================== Auth ====================
    
    @router.post("/auth/login")
    async def admin_login(body: LoginRequest):
        """Login to admin panel"""
        token = create_admin_session(body.access_key)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid access key")
        
        await log_admin_action(db, "login", {"success": True})
        return {"ok": True, "token": token}
    
    @router.post("/auth/logout")
    async def admin_logout(request: Request):
        """Logout from admin panel"""
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            revoke_session(token)
        
        return {"ok": True}
    
    @router.get("/auth/check")
    async def auth_check(_: bool = Depends(require_admin)):
        """Check if authenticated"""
        return {"ok": True, "authenticated": True}
    
    # ==================== Dashboard ====================
    
    @router.get("/dashboard")
    async def dashboard(_: bool = Depends(require_admin)):
        """Get dashboard statistics"""
        return await get_dashboard_stats(db)
    
    # ==================== Channels ====================
    
    @router.get("/channels")
    async def list_channels(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        status: Optional[str] = None,
        search: Optional[str] = None,
        _: bool = Depends(require_admin)
    ):
        """List channels"""
        return await get_channels(db, page, limit, status, search)
    
    @router.post("/channels")
    async def create_channel(body: AddChannelRequest, _: bool = Depends(require_admin)):
        """Add new channel"""
        result = await add_channel(db, body.username, body.priority, body.tags)
        if result.get("ok"):
            await log_admin_action(db, "add_channel", {"username": body.username})
        return result
    
    @router.patch("/channels/{username}")
    async def modify_channel(
        username: str,
        body: UpdateChannelRequest,
        _: bool = Depends(require_admin)
    ):
        """Update channel settings"""
        result = await update_channel(
            db, username, body.enabled, body.priority, body.tags
        )
        if result.get("ok"):
            await log_admin_action(db, "update_channel", {
                "username": username,
                "changes": body.model_dump(exclude_none=True)
            })
        return result
    
    @router.delete("/channels/{username}")
    async def remove_channel(username: str, _: bool = Depends(require_admin)):
        """Delete channel"""
        result = await delete_channel(db, username)
        if result.get("ok"):
            await log_admin_action(db, "delete_channel", {"username": username})
        return result
    
    @router.get("/channels/search/{username}")
    async def search_channel(username: str, _: bool = Depends(require_admin)):
        """
        Live search channel via MTProto
        GET /api/geo-admin/channels/search/:username
        """
        return await search_channel_live(db, username)
    
    @router.get("/channels/{username}/stats")
    async def channel_stats(username: str, _: bool = Depends(require_admin)):
        """Get channel statistics"""
        return await get_channel_stats(db, username)
    
    @router.get("/channels/{username}/posts")
    async def channel_posts(
        username: str, 
        limit: int = Query(50, ge=1, le=200),
        _: bool = Depends(require_admin)
    ):
        """
        Get posts for a channel from database
        GET /api/geo-admin/channels/:username/posts
        """
        try:
            clean_username = username.lower().replace('@', '')
            
            # Get posts from tg_posts collection
            cursor = db.tg_posts.find(
                {"username": clean_username},
                {"_id": 0}
            ).sort("date", -1).limit(limit)
            
            posts = await cursor.to_list(length=limit)
            
            return {
                "ok": True,
                "username": clean_username,
                "count": len(posts),
                "posts": posts
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    @router.post("/channels/{username}/sync")
    async def sync_channel_posts(
        username: str,
        limit: int = Query(50, ge=1, le=200),
        _: bool = Depends(require_admin)
    ):
        """
        Sync posts from Telegram via MTProto
        POST /api/geo-admin/channels/:username/sync
        """
        try:
            from telegram_lite.mtproto_client import MTProtoConnection
            
            clean_username = username.lower().replace('@', '')
            
            async with MTProtoConnection() as client:
                messages = await client.get_channel_messages(clean_username, limit=limit, download_media=False, db=db)
                
                if not messages:
                    return {"ok": False, "error": "No messages returned"}
                
                # Save posts to database
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                saved_count = 0
                
                for msg in messages:
                    post_data = {
                        "username": clean_username,
                        "messageId": msg['messageId'],
                        "date": msg['date'],
                        "text": msg['text'][:2000] if msg['text'] else '',
                        "views": msg['views'],
                        "forwards": msg['forwards'],
                        "replies": msg['replies'],
                        "reactions": msg.get('reactions', {"total": 0, "items": []}),
                        "hasMedia": msg['hasMedia'],
                        "mediaType": msg.get('mediaType'),
                        "fetchedAt": now,
                    }
                    
                    result = await db.tg_posts.update_one(
                        {"username": clean_username, "messageId": msg['messageId']},
                        {"$set": post_data},
                        upsert=True
                    )
                    if result.upserted_id:
                        saved_count += 1
                
                # Update channel lastParsedAt
                await db.geo_channels.update_one(
                    {"username": clean_username},
                    {"$set": {"lastParsedAt": now, "postsCount": len(messages)}}
                )
                
                return {
                    "ok": True,
                    "synced": len(messages),
                    "savedNew": saved_count,
                    "username": clean_username
                }
                
        except Exception as e:
            return {"ok": False, "error": str(e)}
    
    # ==================== Users ====================
    
    @router.get("/users")
    async def list_users(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        radar_enabled: Optional[bool] = None,
        search: Optional[str] = None,
        _: bool = Depends(require_admin)
    ):
        """List bot users"""
        return await get_users(db, page, limit, radar_enabled, search)
    
    @router.get("/users/analytics")
    async def users_analytics(_: bool = Depends(require_admin)):
        """Get user analytics"""
        return await get_user_analytics(db)
    
    @router.get("/users/{actor_id}")
    async def user_details(actor_id: str, _: bool = Depends(require_admin)):
        """Get user details"""
        return await get_user_details(db, actor_id)
    
    # ==================== Bot ====================
    
    @router.get("/bot/status")
    async def bot_status(_: bool = Depends(require_admin)):
        """Get bot status"""
        return await get_bot_status(db)
    
    @router.post("/bot/webhook")
    async def bot_set_webhook(body: WebhookRequest, _: bool = Depends(require_admin)):
        """Set bot webhook"""
        result = await set_webhook(body.url)
        if result.get("ok"):
            await log_admin_action(db, "set_webhook", {"url": body.url})
        return result
    
    @router.delete("/bot/webhook")
    async def bot_delete_webhook(_: bool = Depends(require_admin)):
        """Delete bot webhook"""
        result = await delete_webhook()
        if result.get("ok"):
            await log_admin_action(db, "delete_webhook", {})
        return result
    
    @router.post("/bot/test-message")
    async def bot_test_message(body: TestMessageRequest, _: bool = Depends(require_admin)):
        """Send test message"""
        return await send_test_message(db, body.chat_id, body.message)
    
    @router.get("/bot/delivery-queue")
    async def bot_delivery_queue(
        status: str = "PENDING",
        limit: int = 50,
        _: bool = Depends(require_admin)
    ):
        """Get delivery queue"""
        return await get_delivery_queue(db, status, limit)
    
    @router.post("/bot/retry-failed")
    async def bot_retry_failed(_: bool = Depends(require_admin)):
        """Retry failed deliveries"""
        result = await retry_failed_deliveries(db)
        if result.get("ok"):
            await log_admin_action(db, "retry_failed_deliveries", {"count": result.get("retriedCount")})
        return result
    
    # ==================== Sessions ====================
    
    @router.get("/sessions")
    async def list_sessions(_: bool = Depends(require_admin)):
        """List MTProto sessions"""
        return await get_sessions(db)
    
    @router.get("/sessions/stats")
    async def sessions_stats(_: bool = Depends(require_admin)):
        """Get session statistics"""
        return await get_session_stats(db)
    
    @router.post("/sessions")
    async def create_session(body: AddSessionRequest, _: bool = Depends(require_admin)):
        """Add new MTProto session"""
        result = await add_session(
            db, body.name, body.session_string, body.api_id, body.api_hash,
            body.max_threads, body.channels_limit
        )
        if result.get("ok"):
            await log_admin_action(db, "add_session", {"name": body.name})
        return result
    
    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: str, _: bool = Depends(require_admin)):
        """Remove MTProto session"""
        result = await remove_session(db, session_id)
        if result.get("ok"):
            await log_admin_action(db, "remove_session", {"sessionId": session_id})
        return result
    
    @router.post("/sessions/{session_id}/test")
    async def test_session_endpoint(session_id: str, _: bool = Depends(require_admin)):
        """Test session validity"""
        return await test_session(db, session_id)
    
    # ==================== Signals ====================
    
    @router.get("/signals")
    async def list_signals(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        search: Optional[str] = None,
        hours: int = Query(24, ge=1, le=168),
        sort_by: str = "createdAt",
        sort_dir: str = "desc",
        _: bool = Depends(require_admin)
    ):
        """List signals with filtering"""
        return await get_signals(db, page, limit, status, event_type, search, hours, sort_by, sort_dir)
    
    @router.get("/signals/event-types")
    async def get_event_types(_: bool = Depends(require_admin)):
        """Get available event types"""
        return {"ok": True, "eventTypes": EVENT_TYPES}
    
    @router.get("/signals/{signal_id}")
    async def get_signal(signal_id: str, _: bool = Depends(require_admin)):
        """Get signal by ID"""
        return await get_signal_by_id(db, signal_id)
    
    @router.post("/signals")
    async def create_signal(body: CreateSignalRequest, _: bool = Depends(require_admin)):
        """Create manual signal"""
        result = await create_manual_signal(
            db, body.event_type, body.lat, body.lng,
            body.title, body.description, body.address, body.truth_score
        )
        if result.get("ok"):
            await log_admin_action(db, "create_signal", {"eventType": body.event_type})
        return result
    
    @router.patch("/signals/{signal_id}")
    async def modify_signal(
        signal_id: str,
        body: UpdateSignalRequest,
        _: bool = Depends(require_admin)
    ):
        """Update signal"""
        result = await update_signal(
            db, signal_id, body.event_type, body.title, body.description,
            body.lat, body.lng, body.address, body.truth_score
        )
        if result.get("ok"):
            await log_admin_action(db, "update_signal", {"signalId": signal_id})
        return result
    
    @router.post("/signals/{signal_id}/confirm")
    async def confirm_signal_endpoint(
        signal_id: str,
        body: SignalActionRequest = None,
        _: bool = Depends(require_admin)
    ):
        """Confirm signal"""
        note = body.note if body else None
        result = await confirm_signal(db, signal_id, note)
        if result.get("ok"):
            await log_admin_action(db, "confirm_signal", {"signalId": signal_id})
        return result
    
    @router.post("/signals/{signal_id}/dismiss")
    async def dismiss_signal_endpoint(
        signal_id: str,
        body: SignalActionRequest = None,
        _: bool = Depends(require_admin)
    ):
        """Dismiss signal"""
        reason = body.reason if body else None
        result = await dismiss_signal(db, signal_id, reason)
        if result.get("ok"):
            await log_admin_action(db, "dismiss_signal", {"signalId": signal_id})
        return result
    
    @router.delete("/signals/{signal_id}")
    async def remove_signal(signal_id: str, _: bool = Depends(require_admin)):
        """Delete signal"""
        result = await delete_signal(db, signal_id)
        if result.get("ok"):
            await log_admin_action(db, "delete_signal", {"signalId": signal_id})
        return result
    
    @router.post("/signals/merge")
    async def merge_signals_endpoint(body: MergeSignalsRequest, _: bool = Depends(require_admin)):
        """Merge multiple signals"""
        result = await merge_signals(db, body.signal_ids, body.primary_signal_id)
        if result.get("ok"):
            await log_admin_action(db, "merge_signals", {
                "primaryId": body.primary_signal_id,
                "mergedCount": result.get("mergedCount")
            })
        return result
    
    @router.post("/signals/bulk-status")
    async def bulk_status_endpoint(body: BulkStatusRequest, _: bool = Depends(require_admin)):
        """Bulk update signal status"""
        result = await bulk_update_status(db, body.signal_ids, body.status)
        if result.get("ok"):
            await log_admin_action(db, "bulk_status", {
                "count": result.get("modifiedCount"),
                "status": body.status
            })
        return result
    
    # ==================== Analytics ====================
    
    @router.get("/analytics/events-by-day")
    async def analytics_events_by_day(
        days: int = Query(30, ge=1, le=90),
        _: bool = Depends(require_admin)
    ):
        """Get events by day"""
        return await get_events_by_day(db, days)
    
    @router.get("/analytics/top-event-types")
    async def analytics_top_types(
        days: int = Query(30, ge=1, le=90),
        limit: int = Query(20, ge=1, le=50),
        _: bool = Depends(require_admin)
    ):
        """Get top event types"""
        return await get_top_event_types(db, days, limit)
    
    @router.get("/analytics/top-districts")
    async def analytics_top_districts(
        days: int = Query(30, ge=1, le=90),
        limit: int = Query(20, ge=1, le=50),
        _: bool = Depends(require_admin)
    ):
        """Get top districts"""
        return await get_top_districts(db, days, limit)
    
    @router.get("/analytics/source-breakdown")
    async def analytics_source_breakdown(
        days: int = Query(30, ge=1, le=90),
        _: bool = Depends(require_admin)
    ):
        """Get source breakdown"""
        return await get_source_breakdown(db, days)
    
    @router.get("/analytics/alerts")
    async def analytics_alerts(
        days: int = Query(30, ge=1, le=90),
        _: bool = Depends(require_admin)
    ):
        """Get alert analytics"""
        return await get_alert_analytics(db, days)
    
    @router.get("/analytics/channel-performance")
    async def analytics_channel_perf(
        days: int = Query(30, ge=1, le=90),
        limit: int = Query(20, ge=1, le=50),
        _: bool = Depends(require_admin)
    ):
        """Get channel performance"""
        return await get_channel_performance(db, days, limit)
    
    # ==================== Logs ====================
    
    @router.get("/logs/admin")
    async def logs_admin(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        action_type: Optional[str] = None,
        days: int = Query(7, ge=1, le=30),
        _: bool = Depends(require_admin)
    ):
        """Get admin action logs"""
        return await get_admin_logs(db, page, limit, action_type, days)
    
    @router.get("/logs/parsing")
    async def logs_parsing(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        status: Optional[str] = None,
        days: int = Query(3, ge=1, le=30),
        _: bool = Depends(require_admin)
    ):
        """Get parsing logs"""
        return await get_parsing_logs(db, page, limit, status, days)
    
    @router.get("/logs/delivery")
    async def logs_delivery(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=100),
        status: Optional[str] = None,
        days: int = Query(3, ge=1, le=30),
        _: bool = Depends(require_admin)
    ):
        """Get delivery logs"""
        return await get_delivery_logs(db, page, limit, status, days)
    
    @router.get("/logs/errors")
    async def logs_errors(
        days: int = Query(7, ge=1, le=30),
        _: bool = Depends(require_admin)
    ):
        """Get error summary"""
        return await get_error_summary(db, days)
    
    # ==================== Revenue & Referrals ====================
    
    @router.get("/revenue/stats")
    async def revenue_stats(
        days: int = Query(30, ge=1, le=90),
        _: bool = Depends(require_admin)
    ):
        """Get revenue statistics"""
        from geo_intel.services.subscription_service import PaymentService
        payment_svc = PaymentService(db)
        return await payment_svc.get_payment_stats(days)
    
    @router.get("/revenue/referral-stats")
    async def referral_stats(
        days: int = Query(30, ge=1, le=90),
        _: bool = Depends(require_admin)
    ):
        """Get referral program statistics"""
        from geo_intel.services.wallet_service import PayoutService
        payout_svc = PayoutService(db)
        return await payout_svc.get_payout_stats(days)
    
    @router.get("/revenue/top-referrers")
    async def top_referrers(
        limit: int = Query(20, ge=5, le=100),
        _: bool = Depends(require_admin)
    ):
        """Get top referrers leaderboard"""
        from geo_intel.services.referral_service import ReferralService
        referral_svc = ReferralService(db)
        leaders = await referral_svc.get_referral_leaderboard(limit)
        return {"ok": True, "items": leaders}
    
    @router.get("/payouts/pending")
    async def pending_payouts(
        limit: int = Query(50, ge=10, le=100),
        _: bool = Depends(require_admin)
    ):
        """Get pending payout requests"""
        from geo_intel.services.wallet_service import PayoutService
        payout_svc = PayoutService(db)
        payouts = await payout_svc.get_pending_payouts(limit)
        return {"ok": True, "items": payouts, "count": len(payouts)}
    
    @router.get("/payouts/all")
    async def all_payouts(
        status: Optional[str] = None,
        limit: int = Query(50, ge=10, le=100),
        _: bool = Depends(require_admin)
    ):
        """Get all payouts"""
        query = {}
        if status:
            query["status"] = status
        
        payouts = await db.payouts.find(query, {"_id": 0}).sort("createdAt", -1).limit(limit).to_list(limit)
        return {"ok": True, "items": payouts}
    
    @router.post("/payouts/{payout_id}/approve")
    async def approve_payout(
        payout_id: str,
        body: Dict[str, Any],
        _: bool = Depends(require_admin)
    ):
        """Approve and process payout"""
        from geo_intel.services.wallet_service import PayoutService
        payout_svc = PayoutService(db)
        return await payout_svc.approve_payout(
            payout_id=payout_id,
            tx_hash=body.get("tx_hash"),
            notes=body.get("notes", "")
        )
    
    @router.post("/payouts/{payout_id}/reject")
    async def reject_payout(
        payout_id: str,
        body: Dict[str, Any],
        _: bool = Depends(require_admin)
    ):
        """Reject payout and refund user"""
        from geo_intel.services.wallet_service import PayoutService
        payout_svc = PayoutService(db)
        return await payout_svc.reject_payout(
            payout_id=payout_id,
            reason=body.get("reason", "")
        )
    
    # ==================== Broadcast ====================
    
    @router.post("/broadcast/send")
    async def broadcast_send(
        body: Dict[str, Any],
        _: bool = Depends(require_admin)
    ):
        """Send broadcast message to users"""
        from geo_intel.services.broadcast_service import BroadcastService
        broadcast_svc = BroadcastService(db)
        return await broadcast_svc.broadcast(
            text=body.get("text", ""),
            target=body.get("target", "all"),
            parse_mode=body.get("parse_mode", "Markdown"),
            test_mode=body.get("test_mode", False)
        )
    
    @router.post("/broadcast/test")
    async def broadcast_test(
        body: Dict[str, Any],
        _: bool = Depends(require_admin)
    ):
        """Test broadcast - get target user count without sending"""
        from geo_intel.services.broadcast_service import BroadcastService
        broadcast_svc = BroadcastService(db)
        return await broadcast_svc.broadcast(
            text=body.get("text", ""),
            target=body.get("target", "all"),
            test_mode=True
        )
    
    @router.get("/broadcast/history")
    async def broadcast_history(
        limit: int = Query(20, ge=5, le=100),
        _: bool = Depends(require_admin)
    ):
        """Get broadcast history"""
        from geo_intel.services.broadcast_service import BroadcastService
        broadcast_svc = BroadcastService(db)
        history = await broadcast_svc.get_broadcast_history(limit)
        return {"ok": True, "items": history}
    
    @router.get("/broadcast/{broadcast_id}")
    async def broadcast_status(
        broadcast_id: str,
        _: bool = Depends(require_admin)
    ):
        """Get broadcast status"""
        from geo_intel.services.broadcast_service import BroadcastService
        broadcast_svc = BroadcastService(db)
        status = await broadcast_svc.get_broadcast_status(broadcast_id)
        if status:
            return {"ok": True, "broadcast": status}
        return {"ok": False, "error": "Broadcast not found"}
    
    return router
