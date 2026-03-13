"""
Telegram Intel - Core Type Contracts
Version: 1.0.0 (FROZEN)

WARNING: Do not modify these types after freeze.
If changes needed, create v2 types.

SECURITY: Do not log session_string under any circumstances.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


# ============================================
# REACTION TYPES
# ============================================

class ReactionItem(BaseModel):
    """Single reaction emoji with count"""
    emoji: str
    count: int


class PostReactions(BaseModel):
    """Normalized reactions structure"""
    total: int = 0
    items: List[ReactionItem] = Field(default_factory=list)
    
    # Computed for display
    top: List[ReactionItem] = Field(default_factory=list)  # Top 3
    extraCount: int = 0  # Items beyond top 3


# ============================================
# POST METRICS (FROZEN)
# ============================================

class PostMetrics(BaseModel):
    """Core post metrics - FROZEN"""
    views: int = 0
    forwards: int = 0
    replies: int = 0
    reactions: PostReactions = Field(default_factory=PostReactions)


# ============================================
# MEDIA PAYLOAD
# ============================================

class MediaPayload(BaseModel):
    """Media attachment info"""
    type: str  # photo, video, document
    url: str
    mimeType: Optional[str] = None
    size: Optional[int] = None
    durationSec: Optional[int] = None


# ============================================
# FEED POST (FROZEN CONTRACT)
# ============================================

class FeedPost(BaseModel):
    """
    Single post in feed - FROZEN CONTRACT v1.0.0
    
    This is the primary post type returned by all APIs.
    Do not add/remove fields after v1.0.0
    
    NO PLATFORM-SPECIFIC FIELDS ALLOWED:
    - No uiScore, platformTag, fractalMeta
    - Only pure Telegram data
    """
    # Core identity
    messageId: int
    username: str
    date: str  # ISO format
    text: str
    
    # Metrics (FROZEN structure)
    metrics: PostMetrics = Field(default_factory=PostMetrics)
    
    # Convenience accessors (mirror metrics for backward compat)
    views: int = 0
    forwards: int = 0
    replies: int = 0
    reactions: PostReactions = Field(default_factory=PostReactions)
    
    # Media
    hasMedia: bool = False
    media: Optional[MediaPayload] = None
    
    # Channel info (for feed display only)
    channelTitle: Optional[str] = None
    channelAvatar: Optional[str] = None
    
    # Intelligence (Telegram-specific)
    feedScore: float = 0.0
    anomalyScore: Optional[float] = None
    isAnomaly: bool = False
    
    # User state
    isPinned: bool = False
    isRead: bool = False


# ============================================
# CHANNEL TYPES
# ============================================

class ChannelProfile(BaseModel):
    """Channel basic profile"""
    username: str
    title: str
    description: Optional[str] = None
    members: int = 0
    avatarUrl: Optional[str] = None
    isChannel: bool = True
    isVerified: bool = False
    createdAt: Optional[str] = None


class ChannelMetrics(BaseModel):
    """Channel computed metrics"""
    utilityScore: float = 50.0
    tier: str = "C"
    tierLabel: str = "Average"
    
    # Score breakdown
    scoreBreakdown: Dict[str, float] = Field(default_factory=dict)
    formula: Optional[str] = None
    
    # Activity
    postsPerDay: float = 0.0
    avgViews: int = 0
    engagementRate: float = 0.0
    
    # Growth
    growth7: Optional[float] = None
    growth30: Optional[float] = None


class NetworkNode(BaseModel):
    """Related channel in network"""
    username: str
    title: Optional[str] = None
    avatar: Optional[str] = None
    members: int = 0
    weight: int = 1  # Mention count


# ============================================
# ALERT TYPES
# ============================================

class AlertPayload(BaseModel):
    """
    Alert notification payload - FROZEN
    
    Used for bot delivery and notifications
    """
    alertId: str
    alertType: str  # spike, anomaly, mention, digest
    severity: str = "info"  # info, warning, critical
    
    # Content
    title: str
    message: str
    
    # Reference
    channelUsername: Optional[str] = None
    messageId: Optional[int] = None
    postUrl: Optional[str] = None
    
    # Metadata
    createdAt: str  # ISO format
    data: Dict[str, Any] = Field(default_factory=dict)
