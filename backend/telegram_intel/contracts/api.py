"""
Telegram Intel - API Response Contracts
Version: 1.0.0 (FROZEN)

These are the EXACT response shapes for all public endpoints.
Do not modify after freeze.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from .types import FeedPost, ChannelProfile, ChannelMetrics, NetworkNode, AlertPayload


# ============================================
# FEED API
# ============================================

class FeedResponse(BaseModel):
    """
    GET /api/telegram-intel/feed/v2
    
    FROZEN CONTRACT
    """
    ok: bool = True
    items: List[FeedPost] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    pages: int = 1
    hasMore: bool = False
    
    # Metadata
    actorId: Optional[str] = None
    windowDays: int = 7


class FeedStatsResponse(BaseModel):
    """
    GET /api/telegram-intel/feed/stats
    """
    ok: bool = True
    channelsInFeed: int = 0
    postsToday: int = 0
    mediaCount: int = 0
    avgViews: int = 0
    pinnedCount: int = 0
    unreadCount: int = 0
    hoursWindow: int = 24


class FeedSummaryResponse(BaseModel):
    """
    GET /api/telegram-intel/feed/summary
    """
    ok: bool = True
    summary: Optional[str] = None
    postsAnalyzed: int = 0
    channelsCount: int = 0
    hoursWindow: int = 24
    error: Optional[str] = None


# ============================================
# CHANNEL API
# ============================================

class ChannelNetworkData(BaseModel):
    """Network connections for channel"""
    outgoing: List[NetworkNode] = Field(default_factory=list)
    incoming: List[NetworkNode] = Field(default_factory=list)


class ChannelResponse(BaseModel):
    """
    GET /api/telegram-intel/channel/{username}/full
    
    FROZEN CONTRACT
    """
    ok: bool = True
    channel: Optional[ChannelProfile] = None
    metrics: Optional[ChannelMetrics] = None
    
    # Timeline data
    posts: List[FeedPost] = Field(default_factory=list)
    membersTimeline: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Network
    network: ChannelNetworkData = Field(default_factory=ChannelNetworkData)
    
    # Activity
    activity: Dict[str, Any] = Field(default_factory=dict)
    growth: Dict[str, Any] = Field(default_factory=dict)
    
    # Snapshot
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class ChannelListResponse(BaseModel):
    """
    GET /api/telegram-intel/utility/list
    """
    ok: bool = True
    items: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


# ============================================
# WATCHLIST API
# ============================================

class WatchlistItem(BaseModel):
    """Single watchlist entry"""
    username: str
    addedAt: Optional[str] = None
    actorId: Optional[str] = None


class WatchlistResponse(BaseModel):
    """
    GET /api/telegram-intel/watchlist
    """
    ok: bool = True
    items: List[WatchlistItem] = Field(default_factory=list)
    total: int = 0


# ============================================
# ALERTS API
# ============================================

class AlertsResponse(BaseModel):
    """
    GET /api/telegram-intel/alerts
    """
    ok: bool = True
    actorId: str = "default"
    count: int = 0
    alerts: List[AlertPayload] = Field(default_factory=list)


# ============================================
# BOT API
# ============================================

class BotInfo(BaseModel):
    """Bot basic info"""
    username: Optional[str] = None
    firstName: Optional[str] = None
    canJoinGroups: Optional[bool] = None
    canReadAllGroupMessages: Optional[bool] = None


class WebhookInfo(BaseModel):
    """Webhook status"""
    active: bool = False
    url: Optional[str] = None
    hasCustomCertificate: bool = False
    pendingUpdateCount: int = 0
    lastErrorDate: Optional[int] = None
    lastErrorMessage: Optional[str] = None


class DeliveryStats(BaseModel):
    """Delivery system stats"""
    linkedUsers: int = 0
    pendingMessages: int = 0
    sentMessages: int = 0
    failedMessages: int = 0


class BotStatusResponse(BaseModel):
    """
    GET /api/telegram-intel/bot/status
    
    FROZEN CONTRACT
    """
    ok: bool = True
    botConfigured: bool = False
    botInfo: Optional[BotInfo] = None
    webhook: WebhookInfo = Field(default_factory=WebhookInfo)
    delivery: DeliveryStats = Field(default_factory=DeliveryStats)
    requirements: Dict[str, Any] = Field(default_factory=dict)


# ============================================
# SIGNALS API
# ============================================

class CrossChannelSignal(BaseModel):
    """Cross-channel signal event"""
    topic: str
    channels: List[str] = Field(default_factory=list)
    channelCount: int = 0
    totalMentions: int = 0
    avgViews: int = 0
    isStrongSignal: bool = False


class SignalsResponse(BaseModel):
    """
    GET /api/telegram-intel/signals/cross-channel
    """
    ok: bool = True
    windowMinutes: int = 30
    eventCount: int = 0
    events: List[CrossChannelSignal] = Field(default_factory=list)


# ============================================
# HEALTH API
# ============================================

class HealthResponse(BaseModel):
    """
    GET /api/telegram-intel/health
    """
    ok: bool = True
    module: str = "telegram-intel"
    version: str = "1.0.0"
    runtime: Dict[str, Any] = Field(default_factory=dict)
