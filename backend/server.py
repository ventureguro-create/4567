"""
Telegram Intelligence Backend Server
Python FastAPI wrapper that proxies Telegram Intel requests to Node.js telegram-lite.mjs
"""
from fastapi import FastAPI, APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from cryptography.fernet import Fernet
import os
import logging
import httpx
import asyncio
import subprocess
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import random
import math

# Import LLM for AI Summary
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False

# Import Geo Intel Module
try:
    from geo_intel import GeoModule, GeoConfig
    GEO_INTEL_AVAILABLE = True
except ImportError as e:
    GEO_INTEL_AVAILABLE = False
    print(f"Geo Intel module not available: {e}")

# Import Geo Admin Module
try:
    from geo_admin import build_admin_router
    GEO_ADMIN_AVAILABLE = True
except ImportError as e:
    GEO_ADMIN_AVAILABLE = False
    print(f"Geo Admin module not available: {e}")

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'telegram_intel')]

# Node.js Telegram Lite server URL
TG_LITE_URL = os.environ.get('TG_LITE_URL', 'http://localhost:8002')

# Ensure avatar directory exists
AVATAR_DIR = ROOT_DIR / 'public' / 'tg' / 'avatars'
AVATAR_DIR.mkdir(parents=True, exist_ok=True)

# Create the main app
app = FastAPI(title="Telegram Intelligence API")

# CORS middleware - MUST be added before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for avatars
app.mount("/tg", StaticFiles(directory=str(ROOT_DIR / 'public' / 'tg')), name="tg_static")

# Create routers
api_router = APIRouter(prefix="/api")
telegram_router = APIRouter(prefix="/api/telegram-intel")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Module availability flags (set after imports)
MEMBERS_HISTORY_LOADED = False

# ====================== Secrets Management ======================

def load_encrypted_secrets():
    """Load secrets from encrypted file - using same files as mtproto_client.py"""
    key_path = ROOT_DIR / '.secrets' / 'SESSION_KEY.txt'
    secrets_path = ROOT_DIR / '.secrets' / 'mtproto_session.enc'
    
    if not key_path.exists() or not secrets_path.exists():
        logger.warning(f"Secrets files not found: key={key_path.exists()}, enc={secrets_path.exists()}")
        return None
    
    try:
        # Read key - support both "SESSION_KEY=xxx" and plain "xxx" formats
        key = None
        with open(key_path, 'r') as f:
            content = f.read().strip()
            if '=' in content:
                for line in content.split('\n'):
                    if 'SESSION_KEY=' in line or 'KEY=' in line:
                        key = line.split('=', 1)[1].strip()
                        break
            if not key:
                key = content.split('\n')[0].strip()
        
        if not key:
            logger.error("No key found in SESSION_KEY.txt")
            return None
        
        # Decrypt
        fernet = Fernet(key.encode())
        with open(secrets_path, 'rb') as f:
            encrypted = f.read()
        decrypted = fernet.decrypt(encrypted)
        
        import json
        return json.loads(decrypted.decode())
    except Exception as e:
        logger.error(f"Failed to load secrets: {e}")
        return None

SECRETS = load_encrypted_secrets()
if SECRETS:
    logger.info("Loaded encrypted Telegram credentials")

# ====================== Task 1-4 Modules ======================

# Import Media Engine PRO
try:
    from telegram_lite.media_engine import (
        download_media_safe, media_garbage_collector, get_media_stats,
        ensure_media_indexes, MEDIA_ROOT
    )
    MEDIA_ENGINE_AVAILABLE = True
    logger.info("Media Engine PRO loaded")
except ImportError as e:
    MEDIA_ENGINE_AVAILABLE = False
    logger.warning(f"Media Engine not available: {e}")

# Import Scheduler v2
try:
    from telegram_lite.scheduler_v2 import (
        ensure_scheduler_indexes, get_scheduler_state_v2, scheduler_tick_v2,
        ensure_channel_in_queue, update_channel_band
    )
    SCHEDULER_V2_AVAILABLE = True
    logger.info("Scheduler v2 loaded")
except ImportError as e:
    SCHEDULER_V2_AVAILABLE = False
    logger.warning(f"Scheduler v2 not available: {e}")

# Import Auth + Actor system
try:
    from telegram_lite.auth_actor import (
        ensure_auth_indexes, get_or_create_actor, get_actor_info,
        migrate_legacy_watchlist, get_actor_watchlist, 
        add_to_watchlist as actor_add_to_watchlist,
        remove_from_watchlist as actor_remove_from_watchlist, 
        check_in_watchlist, get_feed_states,
        set_post_read, set_post_pinned, get_pinned_posts
    )
    AUTH_ACTOR_AVAILABLE = True
    logger.info("Auth + Actor system loaded")
except ImportError as e:
    AUTH_ACTOR_AVAILABLE = False
    logger.warning(f"Auth system not available: {e}")

# Import Delivery Bot
try:
    from telegram_lite.delivery_bot import (
        ensure_delivery_indexes, create_link_code, get_actor_link_status,
        revoke_actor_link, handle_bot_update, run_delivery_worker,
        distribute_alerts_to_telegram, BOT_TOKEN
    )
    DELIVERY_BOT_AVAILABLE = bool(BOT_TOKEN)
    if DELIVERY_BOT_AVAILABLE:
        logger.info("Delivery Bot loaded")
    else:
        logger.warning("Delivery Bot loaded but BOT_TOKEN not set")
except ImportError as e:
    DELIVERY_BOT_AVAILABLE = False
    logger.warning(f"Delivery Bot not available: {e}")

# ====================== Models ======================

class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

class ChannelRefreshRequest(BaseModel):
    username: str

# ====================== Helper Functions ======================

AVATAR_COLORS = [
    '#1976D2', '#E53935', '#8E24AA', '#43A047', '#1E88E5',
    '#546E7A', '#00897B', '#F4511E', '#3949AB', '#D81B60',
]

# MOCK_CHANNELS removed - only real data now

def generate_avatar_color(username: str) -> str:
    h = sum(ord(c) for c in username)
    return AVATAR_COLORS[h % len(AVATAR_COLORS)]

def format_title(username: str) -> str:
    return username.replace('_', ' ').title()

def compute_activity_label(posts_per_day: float) -> str:
    if posts_per_day >= 3:
        return "High"
    elif posts_per_day >= 1:
        return "Medium"
    return "Low"

def compute_red_flags(fraud_risk: float) -> int:
    if fraud_risk >= 0.7:
        return 4 + random.randint(0, 2)
    elif fraud_risk >= 0.5:
        return 2 + random.randint(0, 1)
    elif fraud_risk >= 0.3:
        return 1 + random.randint(0, 1)
    return int(fraud_risk * 3)

async def compute_real_avg_reach(db, username: str, days: int = 7) -> int:
    """
    Вычисляет РЕАЛЬНЫЙ средний охват из постов за последние N дней.
    Возвращает среднее количество просмотров на пост.
    """
    from datetime import datetime, timedelta
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    pipeline = [
        {"$match": {
            "username": username,
            "date": {"$gte": cutoff},
            "views": {"$gt": 0}
        }},
        {"$group": {
            "_id": None,
            "avgViews": {"$avg": "$views"},
            "totalViews": {"$sum": "$views"},
            "postCount": {"$sum": 1}
        }}
    ]
    
    result = await db.tg_posts.aggregate(pipeline).to_list(1)
    
    if result and result[0].get("avgViews"):
        return int(result[0]["avgViews"])
    
    return 0

def classify_lifecycle(metrics: dict) -> str:
    growth7 = metrics.get('growth7', 0)
    growth30 = metrics.get('growth30', 0)
    utility = metrics.get('utilityScore', 50)
    stability = metrics.get('stability', 0.7)
    
    if growth7 > 15 and growth30 > 20:
        return "EXPANDING"
    elif growth7 > 5 and utility >= 60:
        return "EMERGING"
    elif growth7 < -5:
        return "DECLINING"
    elif utility >= 70 and stability >= 0.7 and growth7 < 5:
        return "MATURE"
    return "STABLE"

def compute_utility_score(
    members: int = 0,
    engagement_rate: float = 0.1,
    growth7: float = 0,
    growth30: float = 0,
    stability: float = 0.7,
    fraud_risk: float = 0.2,
    posts_per_day: float = 1,
    crypto_relevance: float = 0.5,
) -> dict:
    """
    Compute Utility Score (0-100) based on channel metrics.
    
    Formula components:
    1. Size Score (0-25): Based on log10(members), scaled 1K-10M
    2. Engagement Score (0-25): Based on engagement rate (views/members)
    3. Growth Score (0-20): Based on 7d and 30d subscriber growth
    4. Quality Score (0-20): Based on stability and inverse fraud risk
    5. Activity Score (0-10): Based on posts per day
    
    Bonuses:
    - Crypto relevance bonus: +5 if crypto score > 0.3
    - Large audience bonus: +5 if members > 100K
    
    Returns dict with score breakdown.
    """
    breakdown = {}
    
    # 1. Size Score (0-25 points)
    # log10(1K) = 3, log10(10M) = 7, so scale from 3-7
    if members > 0:
        log_members = math.log10(max(1, members))
        size_score = min(25, max(0, (log_members - 3) / 4 * 25))
    else:
        size_score = 0
    breakdown['size'] = round(size_score, 1)
    
    # 2. Engagement Score (0-25 points)
    # Good engagement: 5-15%, excellent: 15%+
    # engagement_rate is already decimal (0.1 = 10%)
    if engagement_rate > 0:
        eng_pct = engagement_rate * 100
        if eng_pct >= 15:
            engagement_score = 25
        elif eng_pct >= 5:
            engagement_score = 15 + (eng_pct - 5) / 10 * 10
        elif eng_pct >= 1:
            engagement_score = 5 + (eng_pct - 1) / 4 * 10
        else:
            engagement_score = eng_pct * 5
    else:
        engagement_score = 0
    breakdown['engagement'] = round(engagement_score, 1)
    
    # 3. Growth Score (0-20 points)
    # Positive growth = good, negative = bad
    growth7_capped = max(-20, min(50, growth7 or 0))
    growth30_capped = max(-30, min(100, growth30 or 0))
    
    # Weight 7d more heavily (60%) than 30d (40%)
    growth_score = (
        (growth7_capped / 50 * 12) +   # Max 12 points from 7d
        (growth30_capped / 100 * 8)     # Max 8 points from 30d
    )
    growth_score = max(0, min(20, growth_score + 10))  # Shift to 0-20 range
    breakdown['growth'] = round(growth_score, 1)
    
    # 4. Quality Score (0-20 points)
    # Based on stability (how consistent are views) and inverse fraud risk
    stability_component = stability * 10  # 0-10 points
    trust_component = (1 - fraud_risk) * 10  # 0-10 points
    quality_score = stability_component + trust_component
    breakdown['quality'] = round(quality_score, 1)
    
    # 5. Activity Score (0-10 points)
    # 1-3 posts/day = optimal, more is fine but diminishing returns
    if posts_per_day >= 3:
        activity_score = 10
    elif posts_per_day >= 1:
        activity_score = 5 + (posts_per_day - 1) / 2 * 5
    elif posts_per_day >= 0.3:
        activity_score = posts_per_day / 0.3 * 5
    else:
        activity_score = 0
    breakdown['activity'] = round(activity_score, 1)
    
    # Base score (0-100)
    base_score = size_score + engagement_score + growth_score + quality_score + activity_score
    
    # Bonuses
    bonuses = 0
    bonus_reasons = []
    
    # Crypto relevance bonus
    if crypto_relevance > 0.3:
        bonuses += 5
        bonus_reasons.append("Crypto-focused")
    
    # Large audience bonus
    if members > 100000:
        bonuses += 3
        bonus_reasons.append("Large audience")
    elif members > 50000:
        bonuses += 2
        bonus_reasons.append("Growing audience")
    
    # High engagement bonus
    if engagement_rate > 0.2:
        bonuses += 2
        bonus_reasons.append("High engagement")
    
    breakdown['bonuses'] = bonuses
    breakdown['bonusReasons'] = bonus_reasons
    
    # Final score (capped at 100)
    final_score = min(100, max(0, base_score + bonuses))
    
    # Determine tier
    if final_score >= 80:
        tier = 'S'
        tier_label = 'Excellent'
    elif final_score >= 65:
        tier = 'A'
        tier_label = 'Good'
    elif final_score >= 50:
        tier = 'B'
        tier_label = 'Average'
    elif final_score >= 35:
        tier = 'C'
        tier_label = 'Below Average'
    else:
        tier = 'D'
        tier_label = 'Poor'
    
    return {
        'score': round(final_score, 1),
        'tier': tier,
        'tierLabel': tier_label,
        'breakdown': breakdown,
        'formula': 'size(25) + engagement(25) + growth(20) + quality(20) + activity(10) + bonuses'
    }

def generate_sparkline_data(base_value: float, growth: float, points: int = 7) -> list:
    """Generate sparkline data points based on trend"""
    data = []
    current = base_value * (1 - growth / 100 * 0.7)  # Start lower if positive growth
    step = (base_value - current) / (points - 1) if points > 1 else 0
    for i in range(points):
        noise = random.uniform(-2, 2)
        data.append(round(current + noise, 1))
        current += step
    return data

# Mock generators removed - only real data from MTProto now

# ====================== Edge Events Extraction ======================
import re

# Regex patterns for mention extraction
RE_AT_MENTION = re.compile(r'(?:^|[^a-zA-Z0-9_])@([a-zA-Z0-9_]{4,64})', re.IGNORECASE)
RE_TME_LINK = re.compile(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{4,64})(?:/|$)', re.IGNORECASE)

def normalize_username(u: str) -> str:
    """Normalize username to lowercase without @"""
    if not u:
        return None
    x = str(u).strip().lower()
    x = re.sub(r'^https?://t\.me/', '', x)
    x = x.lstrip('@')
    x = re.sub(r'/.*', '', x)  # Remove /... after username
    x = re.sub(r'[^\w]', '', x)  # Keep only alphanumeric + underscore
    if len(x) < 4 or len(x) > 64:
        return None
    return x

def extract_mentions_from_text(text: str) -> list:
    """Extract @username and t.me/username mentions from text"""
    if not text:
        return []
    
    mentions = set()
    
    # @username mentions
    for match in RE_AT_MENTION.finditer(text):
        u = normalize_username(match.group(1))
        if u:
            mentions.add(u)
    
    # t.me/username links
    for match in RE_TME_LINK.finditer(text):
        u = normalize_username(match.group(1))
        if u:
            mentions.add(u)
    
    return list(mentions)

async def write_edge_events(username: str, messages: list):
    """Write edge events from messages to tg_edge_events collection"""
    if not messages:
        return 0
    
    username = normalize_username(username)
    if not username:
        return 0
    
    bulk_ops = []
    src = username
    
    for msg in messages:
        text = msg.get('text', '') or ''
        msg_id = str(msg.get('messageId', msg.get('id', '')))
        date = msg.get('date')
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                date = datetime.now(timezone.utc)
        elif not date:
            date = datetime.now(timezone.utc)
        
        # Extract mentions
        targets = extract_mentions_from_text(text)
        
        for dst in targets:
            if not dst or dst == username:
                continue  # Skip self-mentions
            
            bulk_ops.append({
                'updateOne': {
                    'filter': {
                        'src': src,
                        'dst': dst,
                        'msgId': msg_id,
                        'type': 'mention'
                    },
                    'update': {
                        '$set': {
                            'src': src,
                            'dst': dst,
                            'type': 'mention',
                            'msgId': msg_id,
                            'ts': date,
                            'channel': username
                        }
                    },
                    'upsert': True
                }
            })
        
        # Forward extraction (if forwardPeer exists)
        forward_peer = msg.get('forwardPeer')
        if forward_peer:
            fwd_username = None
            if isinstance(forward_peer, str):
                fwd_username = normalize_username(forward_peer)
            elif isinstance(forward_peer, dict):
                fwd_username = normalize_username(forward_peer.get('username', ''))
            
            if fwd_username and fwd_username != username:
                bulk_ops.append({
                    'updateOne': {
                        'filter': {
                            'src': src,
                            'dst': fwd_username,
                            'msgId': msg_id,
                            'type': 'forward'
                        },
                        'update': {
                            '$set': {
                                'src': src,
                                'dst': fwd_username,
                                'type': 'forward',
                                'msgId': msg_id,
                                'ts': date,
                                'channel': username
                            }
                        },
                        'upsert': True
                    }
                })
    
    if bulk_ops:
        try:
            await db.tg_edge_events.bulk_write(bulk_ops, ordered=False)
            logger.info(f"Wrote {len(bulk_ops)} edge events for {username}")
            return len(bulk_ops)
        except Exception as e:
            logger.error(f"Edge events write error: {e}")
            return 0
    
    return 0

async def build_channel_snapshot(username: str, window_days: int = 30):
    """Build aggregated snapshot for channel page"""
    username = normalize_username(username)
    if not username:
        return None
    
    # Use string format for date comparison (posts have string dates)
    since = (datetime.utcnow() - timedelta(days=window_days)).isoformat()
    
    # Get channel profile
    channel = await db.tg_channel_states.find_one({'username': username})
    if not channel:
        return None
    
    # Get posts for window (date stored as ISO string)
    posts = await db.tg_posts.find({
        'username': username,
        'date': {'$gte': since}
    }).sort('date', -1).to_list(1000)
    
    total_posts = len(posts)
    posts_per_day = total_posts / window_days if window_days > 0 else 0
    
    # Views stats
    views = [p.get('views', 0) for p in posts if p.get('views', 0) > 0]
    avg_views = sum(views) / len(views) if views else 0
    
    members = channel.get('participantsCount', 0) or 1
    engagement_rate = avg_views / members if members > 0 else 0
    
    # Stability (coefficient of variation)
    stability = 'stable'
    if len(views) > 5:
        mean = avg_views
        if mean > 0:
            variance = sum((v - mean) ** 2 for v in views) / len(views)
            cv = math.sqrt(variance) / mean
            if cv > 0.5:
                stability = 'volatile'
            elif cv > 0.3:
                stability = 'moderate'
    
    # Daily series
    series_map = {}
    for p in posts:
        d = p.get('date')
        if isinstance(d, datetime):
            day = d.strftime('%Y-%m-%d')
        elif isinstance(d, str):
            day = d[:10]
        else:
            continue
        
        if day not in series_map:
            series_map[day] = {'posts': 0, 'views': 0}
        series_map[day]['posts'] += 1
        series_map[day]['views'] += p.get('views', 0)
    
    series = [
        {'date': d, 'posts': v['posts'], 'views': v['views']}
        for d, v in sorted(series_map.items())
    ]
    
    # Calculate growth from members history
    growth7 = None
    growth30 = None
    members_base7 = None
    members_base30 = None
    
    try:
        if MEMBERS_HISTORY_LOADED:
            growth_data = await calculate_growth(db, username)
            growth7 = growth_data.get('growth7')
            growth30 = growth_data.get('growth30')
            members_base7 = growth_data.get('base7')
            members_base30 = growth_data.get('base30')
            if growth_data.get('currentMembers'):
                members = growth_data['currentMembers']
    except Exception as e:
        logger.warning(f"Growth calculation failed for {username}: {e}")
    
    snapshot = {
        'username': username,
        'windowDays': window_days,
        'ts': datetime.utcnow(),
        
        'members': channel.get('participantsCount', 0),
        'viewsPerPost': round(avg_views, 1),
        'messagesPerDay': round(posts_per_day, 2),
        
        'engagementRate': round(engagement_rate, 4),
        'viewRateStability': stability,
        
        # Growth from members history
        'growth7': round(growth7 * 100, 2) if growth7 is not None else None,  # as percentage
        'growth30': round(growth30 * 100, 2) if growth30 is not None else None,
        'membersBase7': members_base7,
        'membersBase30': members_base30,
        
        'series': series,
        
        'lastPostAt': posts[0].get('date') if posts else None,
        'totalPosts': total_posts,
        
        # Channel profile data
        'title': channel.get('title', username),
        'lang': channel.get('lang', 'en'),
        'cryptoRelevance': channel.get('cryptoRelevanceScore', 0),
    }
    
    # Upsert snapshot
    await db.tg_channel_snapshots.update_one(
        {'username': username, 'windowDays': window_days},
        {'$set': snapshot},
        upsert=True
    )
    
    return snapshot

# ====================== Base API Routes ======================

@api_router.get("/")
async def root():
    return {"message": "Telegram Intelligence API v1.0", "status": "operational"}

@api_router.get("/health")
async def health():
    return {
        "status": "healthy",
        "mongodb": "connected",
        "secrets_loaded": SECRETS is not None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks

# ====================== Telegram Intel Routes ======================

@telegram_router.get("/health")
async def telegram_health():
    return {
        "ok": True,
        "module": "telegram-intel",
        "version": "1.0.0",
        "runtime": {
            "mode": "live",
            "connected": SECRETS is not None
        }
    }

@telegram_router.get("/utility/list")
async def get_utility_list(
    q: Optional[str] = None,
    type: Optional[str] = None,
    sector: Optional[str] = None,
    minMembers: int = 1000,
    maxMembers: Optional[int] = None,
    minGrowth7: Optional[float] = None,
    maxGrowth7: Optional[float] = None,
    activity: Optional[str] = None,
    maxRedFlags: Optional[int] = None,
    lifecycle: Optional[str] = None,
    maxFraud: Optional[float] = None,
    sort: Optional[str] = "utility",
    dir: Optional[str] = "desc",
    page: int = 1,
    limit: int = 25
):
    """
    Get list of Telegram channels - ONLY ELIGIBLE channels with real data
    
    Eligibility criteria:
    - eligible=true OR participantsCount >= 1000
    - participantsCount >= minMembers (default 1000)
    """
    try:
        # STRICT eligibility filter - only real crypto channels
        states_filter = {
            "$or": [
                {"eligibility.status": "ELIGIBLE"},
                {"eligible": True},
                # Also include channels without eligibility field but with enough members
                {"eligibility": {"$exists": False}, "participantsCount": {"$gte": minMembers}},
            ],
            "participantsCount": {"$gte": minMembers},
        }
        
        # Add optional maxMembers filter
        if maxMembers:
            states_filter["participantsCount"]["$lte"] = maxMembers
        
        # Add search filter
        if q:
            search_regex = {"$regex": q.strip(), "$options": "i"}
            states_filter["$or"] = [
                {"username": search_regex},
                {"title": search_regex},
            ]
        
        # Add sector filter
        if sector:
            states_filter["sector"] = sector
        
        # Get states with sorting at DB level
        sort_field = "participantsCount"  # default
        sort_dir = -1 if dir == "desc" else 1
        
        states = await db.tg_channel_states.find(
            states_filter,
            {"_id": 0}
        ).sort(sort_field, sort_dir).to_list(500)
        
        if not states:
            return {
                "ok": True,
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "pages": 1,
                "stats": {"tracked": 0, "avgUtility": 0, "highGrowth": 0, "highRisk": 0},
                "message": "No eligible channels. Use /admin/mtproto/fetch/{username} to add channels."
            }
        
        usernames = [s.get("username") for s in states if s.get("username")]
        
        # Get latest snapshots
        pipeline = [
            {"$match": {"username": {"$in": usernames}}},
            {"$sort": {"date": -1}},
            {"$group": {
                "_id": "$username",
                "utility": {"$first": "$utility"},
                "growth7": {"$first": "$growth7"},
                "growth30": {"$first": "$growth30"},
                "stability": {"$first": "$stability"},
                "fraud": {"$first": "$fraud"},
                "engagement": {"$first": "$engagement"},
                "postsPerDay": {"$first": "$postsPerDay"},
                "date": {"$first": "$date"},
            }}
        ]
        
        snapshots = await db.tg_score_snapshots.aggregate(pipeline).to_list(500)
        snap_map = {s["_id"]: s for s in snapshots}
        
        # Get growth data from members_history
        growth_map = {}
        if MEMBERS_HISTORY_LOADED:
            for username in usernames:
                try:
                    growth_data = await calculate_growth(db, username)
                    growth_map[username] = growth_data
                except:
                    pass
        
        states_map = {s["username"]: s for s in states}
        
        items = []
        for username in usernames:
            state = states_map.get(username, {})
            snap = snap_map.get(username, {})
            growth = growth_map.get(username, {})
            
            members = state.get("participantsCount", 0) or 0
            if members < minMembers:
                continue
            
            # Get real growth from members_history if available
            growth7_val = growth.get("growth7")
            if growth7_val is not None:
                growth7_val = round(growth7_val * 100, 1)  # Convert to percentage
            else:
                growth7_val = snap.get("growth7", 0)
            
            growth30_val = growth.get("growth30")
            if growth30_val is not None:
                growth30_val = round(growth30_val * 100, 1)
            else:
                growth30_val = snap.get("growth30", 0)
            
            utility_score = snap.get("utility", 50)
            fraud_risk = snap.get("fraud", 0.2)
            stability_val = snap.get("stability", 0.7)
            engagement_rate = snap.get("engagement", 0.1)
            posts_per_day = snap.get("postsPerDay", 2)
            
            # Получаем реальный avgReach из постов (сохранённый в state или вычисляем)
            avg_reach = state.get("avgReach") or int(members * engagement_rate)
            
            # Apply optional filters
            if maxFraud is not None and fraud_risk > maxFraud:
                continue
            if minGrowth7 is not None and (growth7_val or 0) < minGrowth7:
                continue
            if maxGrowth7 is not None and (growth7_val or 0) > maxGrowth7:
                continue
            if maxRedFlags is not None and compute_red_flags(fraud_risk) > maxRedFlags:
                continue
            
            # Sparkline
            random.seed(hash(username))
            sparkline = generate_sparkline_data(utility_score, growth7_val or 0, 7)
            
            items.append({
                "username": username,
                "title": state.get("title") or format_title(username),
                "avatarUrl": state.get("avatarUrl"),
                "avatarColor": generate_avatar_color(username),
                "type": "Group" if state.get("isChannel") is False else "Channel",
                "members": members,
                "avgReach": avg_reach,
                "growth7": growth7_val,
                "growth30": growth30_val,
                "activity": compute_activity_label(posts_per_day),
                "activityLabel": compute_activity_label(posts_per_day),
                "redFlags": compute_red_flags(fraud_risk),
                "fomoScore": utility_score,
                "utilityScore": utility_score,
                "engagement": int(engagement_rate * 10000),
                "engagementRate": engagement_rate,
                "lifecycle": classify_lifecycle({
                    "growth7": growth7_val or 0,
                    "growth30": growth30_val or 0,
                    "utilityScore": utility_score,
                    "stability": stability_val
                }),
                "fraudRisk": fraud_risk,
                "stability": stability_val,
                "sparkline": sparkline,
                "likes": sum([
                    1 if (growth7_val or 0) > 0 else 0,
                    1 if engagement_rate > 0.05 else 0,
                    1 if fraud_risk < 0.35 else 0,
                    1 if stability_val > 0.55 else 0,
                    1 if members > 5000 else 0,
                ]),
                "stars": min(5, max(0, round(utility_score / 20))),
                "updatedAt": state.get("updatedAt", datetime.utcnow()).isoformat() if isinstance(state.get("updatedAt"), datetime) else str(state.get("updatedAt", "")),
                # Sector classification
                "sector": state.get("sector"),
                "sectorColor": state.get("sectorColor"),
                "tags": state.get("tags", []),
            })
        
        if not items:
            return {
                "ok": True,
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "pages": 1,
                "stats": {"tracked": 0, "avgUtility": 0, "highGrowth": 0, "highRisk": 0},
                "message": "No channels match your filters."
            }
        
        # Apply type filter
        if type == "channel":
            items = [i for i in items if i["type"] == "Channel"]
        elif type == "group":
            items = [i for i in items if i["type"] == "Group"]
        
        if activity:
            items = [i for i in items if i["activity"] == activity]
        if lifecycle:
            items = [i for i in items if i["lifecycle"] == lifecycle]
        
        # Sort by chosen field
        sort_key = {
            "utility": "utilityScore",
            "score": "utilityScore", 
            "members": "members",
            "growth": "growth7",
            "growth7": "growth7",
            "reach": "avgReach",
        }.get(sort, "utilityScore")
        
        reverse = (dir != "asc")
        items.sort(key=lambda x: x.get(sort_key) or 0, reverse=reverse)
        
        total = len(items)
        start_idx = (page - 1) * limit
        paginated = items[start_idx:start_idx + limit]
        
        # Calculate stats
        high_growth = len([i for i in items if i.get("growth7", 0) > 10])
        high_risk = len([i for i in items if i.get("fraudRisk", 0) > 0.4])
        avg_utility = sum(i.get("utilityScore", 50) for i in items) / len(items) if items else 0
        
        return {
            "ok": True,
            "items": paginated,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if total > 0 else 1,
            "stats": {
                "tracked": total,
                "avgUtility": round(avg_utility),
                "highGrowth": high_growth,
                "highRisk": high_risk
            },
            "filters": {
                "q": q,
                "type": type,
                "activity": activity,
                "lifecycle": lifecycle,
            }
        }
    except Exception as e:
        logger.error(f"Error getting utility list: {e}")
        # Return error - no mock fallback
        return {
            "ok": False,
            "error": str(e),
            "items": [],
            "total": 0,
            "page": 1,
            "limit": limit,
            "pages": 1
        }

@telegram_router.get("/channel/{username}/overview")
async def get_channel_overview(username: str):
    """Get full channel overview data - REAL DATA ONLY"""
    clean_username = username.lower().replace("@", "").replace("https://t.me/", "").replace("t.me/", "").split("/")[0].split("?")[0]
    
    try:
        # Get data from MongoDB
        state = await db.tg_channel_states.find_one({"username": clean_username})
        snapshot = await db.tg_score_snapshots.find_one(
            {"username": clean_username},
            sort=[("date", -1)]
        )
        
        if not state:
            return {
                "ok": False,
                "error": "NOT_FOUND",
                "message": f"Channel @{clean_username} not found. Fetch it first: /admin/mtproto/fetch/{clean_username}"
            }
        
        # Get posts
        posts = await db.tg_posts.find(
            {"username": clean_username}
        ).sort("date", -1).limit(50).to_list(50)
        
        # Get network data
        network = None
        if NETWORK_LOADED:
            try:
                network = await get_channel_network_edges(db, clean_username, 30)
            except:
                pass
        
        # Get REAL growth from members_history
        growth7 = 0
        growth30 = 0
        if MEMBERS_HISTORY_LOADED:
            try:
                growth_data = await calculate_growth(db, clean_username)
                if growth_data.get("growth7") is not None:
                    growth7 = round(growth_data.get("growth7", 0) * 100, 2)
                if growth_data.get("growth30") is not None:
                    growth30 = round(growth_data.get("growth30", 0) * 100, 2)
            except Exception as e:
                logger.warning(f"Growth calculation failed: {e}")
                growth7 = snapshot.get("growth7", 0) if snapshot else 0
                growth30 = snapshot.get("growth30", 0) if snapshot else 0
        else:
            growth7 = snapshot.get("growth7", 0) if snapshot else 0
            growth30 = snapshot.get("growth30", 0) if snapshot else 0
        
        # Build real data response
        members = state.get("participantsCount", 0) or 0
        utility_score = snapshot.get("utility", 50) if snapshot else 50
        fraud_risk = snapshot.get("fraud", 0.2) if snapshot else 0.2
        stability = snapshot.get("stability", 0.7) if snapshot else 0.7
        engagement = snapshot.get("engagement", 0.1) if snapshot else 0.1
        posts_per_day = snapshot.get("postsPerDay", 1) if snapshot else 1
        
        # Calculate quality signals for "likes"
        quality_likes = 0
        if growth7 > 0: quality_likes += 1
        if engagement > 0.05: quality_likes += 1
        if fraud_risk < 0.35: quality_likes += 1
        if stability > 0.55: quality_likes += 1
        if members > 5000: quality_likes += 1
        
        # Stars from utility (0-5)
        stars = min(5, max(0, round(utility_score / 20)))
        
        now = datetime.now(timezone.utc)
        
        # Recent posts formatted
        recent_posts = []
        for p in posts[:10]:
            post_date = p.get("date")
            if isinstance(post_date, datetime):
                date_str = post_date.isoformat()
            else:
                date_str = str(post_date) if post_date else now.isoformat()
            
            # Extract real messageId for Telegram link
            msg_id = p.get("messageId")
            if msg_id:
                # Clean up messageId if it contains prefix
                msg_id_str = str(msg_id)
                if '_' in msg_id_str:
                    # Format: "username_0_timestamp" -> extract numeric part if exists
                    parts = msg_id_str.split('_')
                    # Try to find a purely numeric part
                    for part in parts:
                        if part.isdigit():
                            msg_id = part
                            break
            
            recent_posts.append({
                "id": str(p.get("messageId", uuid.uuid4())),
                "messageId": msg_id if isinstance(msg_id, (int, str)) and str(msg_id).isdigit() else None,
                "username": clean_username,
                "date": date_str,
                "text": p.get("text") or "",  # Full text, will be truncated on frontend
                "views": p.get("views", 0),
                "forwards": p.get("forwards", 0),
                "replies": p.get("replies", 0),
                "reactions": p.get("reactions", 0),
            })
        
        return {
            "ok": True,
            "profile": {
                "username": clean_username,
                "title": state.get("title") or format_title(clean_username),
                "avatarUrl": state.get("avatarUrl"),
                "avatarColor": generate_avatar_color(clean_username),
                "type": "Group" if state.get("isChannel") is False else "Channel",
                "about": state.get("about") or "",
            },
            "topCards": {
                "subscribers": members,
                "viewsPerPost": int(members * engagement),
                "messagesPerDay": posts_per_day,
                "activityLevel": compute_activity_label(posts_per_day),
            },
            "metrics": {
                "utilityScore": utility_score,
                "growth7": growth7,
                "growth30": growth30,
                "engagement": engagement,
                "fraud": fraud_risk,
                "stability": stability,
            },
            "qualitySignals": {
                "likes": quality_likes,
                "stars": stars,
            },
            "audienceSnapshot": {
                "total": members,
                "growth7d": growth7,
                "growth30d": growth30,
                "engagementRate": engagement,
            },
            "activityOverview": {
                "postsPerDay": posts_per_day,
                "activeDays": 7,
                "consistency": stability,
            },
            "healthSafety": {
                "fraudRisk": fraud_risk,
                "stability": stability,
                "redFlags": compute_red_flags(fraud_risk),
                "trustScore": round((1 - fraud_risk) * 100),
            },
            "eligibility": state.get("eligibility", {}),
            "network": network if network else {"inbound": [], "outbound": []},
            "recentPosts": recent_posts,
            "timeline": [],  # TODO: Build from real data
            "relatedChannels": [],  # TODO: Build from network data
        }
    except Exception as e:
        logger.error(f"Error getting channel overview: {e}")
        return {
            "ok": False,
            "error": str(e),
            "message": "Failed to load channel data"
        }

@telegram_router.get("/channel/{username}/full")
async def get_channel_full(username: str):
    """
    Get COMPLETE channel data in one request - ALL real data
    GET /api/telegram-intel/channel/:username/full
    
    Returns: channel, metrics, snapshot, growth, activity, posts, network
    """
    clean_username = username.lower().replace("@", "").replace("https://t.me/", "").replace("t.me/", "").split("/")[0].split("?")[0]
    
    try:
        # Get channel state
        channel = await db.tg_channel_states.find_one(
            {"username": clean_username},
            {"_id": 0}
        )
        
        if not channel:
            return {
                "ok": False,
                "error": "CHANNEL_NOT_FOUND",
                "message": f"Channel @{clean_username} not found. Fetch it first: /admin/mtproto/fetch/{clean_username}"
            }
        
        # Get snapshot
        snapshot = await db.tg_channel_snapshots.find_one(
            {"username": clean_username},
            {"_id": 0},
            sort=[("windowDays", -1)]
        )
        
        # Get score snapshot  
        score_snap = await db.tg_score_snapshots.find_one(
            {"username": clean_username},
            {"_id": 0},
            sort=[("date", -1)]
        )
        
        # Get REAL growth from members_history
        growth_data = {"growth7": None, "growth30": None, "base7": None, "base30": None}
        if MEMBERS_HISTORY_LOADED:
            try:
                growth_data = await calculate_growth(db, clean_username)
            except Exception as e:
                logger.warning(f"Growth calculation failed: {e}")
        
        # Format growth as percentages
        growth7 = round(growth_data.get("growth7", 0) * 100, 2) if growth_data.get("growth7") is not None else None
        growth30 = round(growth_data.get("growth30", 0) * 100, 2) if growth_data.get("growth30") is not None else None
        
        # Get posts (extended limit for timeline analysis)
        posts = await db.tg_posts.find(
            {"username": clean_username},
            {"_id": 0, "messageId": 1, "date": 1, "views": 1, "forwards": 1, "replies": 1, "reactions": 1, "text": 1, "hasMedia": 1}
        ).sort("date", -1).limit(100).to_list(100)
        
        # Get media assets for posts
        post_ids = [p.get("messageId") for p in posts if p.get("messageId")]
        media_assets = {}
        if post_ids:
            media_docs = await db.tg_media_assets.find(
                {"username": clean_username, "messageId": {"$in": post_ids}},
                {"_id": 0, "messageId": 1, "mediaType": 1, "url": 1, "localPath": 1, "mimeType": 1, "fileSize": 1}
            ).to_list(200)
            for m in media_docs:
                mid = m.get("messageId")
                if mid:
                    media_assets[mid] = {
                        "type": m.get("mediaType", "photo"),
                        "url": f"/api/telegram-intel/media/{clean_username}/{mid}",
                        "mimeType": m.get("mimeType"),
                        "size": m.get("fileSize")
                    }
        
        # Ad detection patterns (Russian and English)
        AD_PATTERNS = ['#реклама', '#ad', '#партнер', '#sponsored', 'реклама:', 'на правах рекламы']
        
        # Format posts and detect ads
        formatted_posts = []
        total_ads = 0
        for p in posts:
            post_date = p.get("date")
            if isinstance(post_date, datetime):
                date_str = post_date.isoformat()
            else:
                date_str = str(post_date) if post_date else ""
            
            # Check if post is an ad
            text_lower = (p.get("text") or "").lower()
            is_ad = any(pattern in text_lower for pattern in AD_PATTERNS)
            if is_ad:
                total_ads += 1
            
            msg_id = p.get("messageId")
            media = media_assets.get(msg_id)
            
            # Build reactions with top-3 logic
            raw_reactions = p.get("reactions", {})
            if isinstance(raw_reactions, int):
                reactions_payload = {"total": raw_reactions, "top": [], "extraCount": 0}
            elif isinstance(raw_reactions, dict):
                items = raw_reactions.get("items", [])
                top_3 = items[:3]
                extra_count = max(len(items) - 3, 0)
                reactions_payload = {
                    "total": raw_reactions.get("total", 0),
                    "top": top_3,
                    "extraCount": extra_count
                }
            else:
                reactions_payload = {"total": 0, "top": [], "extraCount": 0}
            
            formatted_posts.append({
                "id": str(msg_id),
                "messageId": msg_id,
                "date": date_str,
                "text": p.get("text", ""),
                "views": p.get("views", 0),
                "forwards": p.get("forwards", 0),
                "replies": p.get("replies", 0),
                "reactions": reactions_payload,
                "isAd": is_ad,
                "hasMedia": p.get("hasMedia") or media is not None,
                "media": media,
            })
        
        # Get members history for Joins calculation (last 90 days)
        members_timeline = []
        if MEMBERS_HISTORY_LOADED:
            try:
                members_timeline = await get_members_history(db, clean_username, days=90)
            except Exception as e:
                logger.warning(f"Members history fetch failed: {e}")
        
        # Get network - OUTGOING mentions with avatar
        outgoing = []
        try:
            # First get edges
            outgoing_agg = await db.tg_edge_events.aggregate([
                {"$match": {"$or": [{"fromUsername": clean_username}, {"source": clean_username}]}},
                {"$group": {"_id": {"$ifNull": ["$toUsername", "$target"]}, "weight": {"$sum": 1}}},
                {"$sort": {"weight": -1}},
                {"$limit": 15},
                {"$project": {"_id": 0, "username": "$_id", "weight": 1}}
            ]).to_list(15)
            
            # Enrich with channel data (avatars)
            for o in outgoing_agg:
                if o.get("username"):
                    related_ch = await db.tg_channel_states.find_one(
                        {"username": o["username"]},
                        {"avatarUrl": 1, "title": 1, "participantsCount": 1, "_id": 0}
                    )
                    outgoing.append({
                        "username": o["username"],
                        "weight": o["weight"],
                        "avatar": related_ch.get("avatarUrl") if related_ch else None,
                        "title": related_ch.get("title") if related_ch else format_title(o["username"]),
                        "members": related_ch.get("participantsCount", 0) if related_ch else 0
                    })
        except Exception as e:
            logger.warning(f"Outgoing network failed: {e}")
        
        # Get network - INCOMING mentions with avatar
        incoming = []
        try:
            incoming_agg = await db.tg_edge_events.aggregate([
                {"$match": {"$or": [{"toUsername": clean_username}, {"target": clean_username}]}},
                {"$group": {"_id": {"$ifNull": ["$fromUsername", "$source"]}, "weight": {"$sum": 1}}},
                {"$sort": {"weight": -1}},
                {"$limit": 15},
                {"$project": {"_id": 0, "username": "$_id", "weight": 1}}
            ]).to_list(15)
            
            # Enrich with channel data (avatars)
            for i in incoming_agg:
                if i.get("username"):
                    related_ch = await db.tg_channel_states.find_one(
                        {"username": i["username"]},
                        {"avatarUrl": 1, "title": 1, "participantsCount": 1, "_id": 0}
                    )
                    incoming.append({
                        "username": i["username"],
                        "weight": i["weight"],
                        "avatar": related_ch.get("avatarUrl") if related_ch else None,
                        "title": related_ch.get("title") if related_ch else format_title(i["username"]),
                        "members": related_ch.get("participantsCount", 0) if related_ch else 0
                    })
        except Exception as e:
            logger.warning(f"Incoming network failed: {e}")
        
        # Extract metrics
        members = channel.get("participantsCount", 0) or 0
        fraud_risk = score_snap.get("fraud", 0.2) if score_snap else 0.2
        stability = score_snap.get("stability", 0.7) if score_snap else 0.7
        engagement_rate = score_snap.get("engagement", 0.1) if score_snap else 0.1
        posts_per_day = snapshot.get("messagesPerDay", 1) if snapshot else 1
        
        # Compute utility score using formula
        utility_result = compute_utility_score(
            members=members,
            engagement_rate=engagement_rate,
            growth7=growth7 or 0,
            growth30=growth30 or 0,
            stability=stability,
            fraud_risk=fraud_risk,
            posts_per_day=posts_per_day,
            crypto_relevance=0.8,  # Assume crypto relevance for Telegram intel
        )
        utility_score = utility_result['score']
        utility_tier = utility_result['tier']
        
        # Build response
        return {
            "ok": True,
            
            "channel": {
                "username": clean_username,
                "title": channel.get("title") or format_title(clean_username),
                "avatarUrl": channel.get("avatarUrl"),
                "avatarColor": generate_avatar_color(clean_username),
                "type": "Group" if channel.get("isChannel") is False else "Channel",
                "about": channel.get("about") or "",
                "members": members,
                "isVerified": channel.get("isVerified", False),
                "lastFetchedAt": channel.get("lastFetchedAt").isoformat() if isinstance(channel.get("lastFetchedAt"), datetime) else None,
                # Sector classification data
                "sector": channel.get("sector"),
                "sectorSecondary": channel.get("sectorSecondary", []),
                "sectorColor": channel.get("sectorColor"),
                "tags": channel.get("tags", []),
            },
            
            "metrics": {
                "members": members,
                "utilityScore": utility_score,
                "tier": utility_tier,
                "tierLabel": utility_result['tierLabel'],
                "fraudRisk": fraud_risk,
                "stability": stability,
                "engagementRate": engagement_rate,
                "scoreBreakdown": utility_result['breakdown'],
                "formula": utility_result['formula'],
            },
            
            "snapshot": snapshot,
            
            "growth": {
                "growth7": growth7,
                "growth30": growth30,
                "base7": growth_data.get("base7"),
                "base30": growth_data.get("base30"),
                "currentMembers": growth_data.get("currentMembers"),
            },
            
            "activity": {
                "postsPerDay": posts_per_day,
                "avgReach24h": await compute_real_avg_reach(db, clean_username, 7) or int(members * engagement_rate),
                "engagementRate": round(engagement_rate * 100, 2),
                "stability": stability,
                "activityLabel": compute_activity_label(posts_per_day),
            },
            
            "posts": formatted_posts[:30],  # Return only 30 for display, full list used for timeline
            
            "membersTimeline": members_timeline,  # For Joins calculation on frontend
            
            "adsStats": {
                "total": total_ads,
                "totalPosts": len(formatted_posts),
            },
            
            "network": {
                "outgoing": outgoing,
                "incoming": incoming,
                "totalOutgoing": len(outgoing),
                "totalIncoming": len(incoming),
            },
            
            "healthSafety": {
                "fraudRisk": fraud_risk,
                "stability": stability,
                "redFlags": compute_red_flags(fraud_risk),
                "trustScore": round((1 - fraud_risk) * 100),
            },
        }
        
    except Exception as e:
        logger.error(f"Error getting channel full: {e}")
        return {
            "ok": False,
            "error": str(e),
            "message": "Failed to load channel data"
        }

@telegram_router.get("/compare")
async def compare_channels(left: str, right: str):
    """Compare two channels"""
    left_data = await get_channel_overview(left)
    right_data = await get_channel_overview(right)
    
    # Calculate diffs for compare modal
    left_metrics = left_data.get("metrics", {})
    right_metrics = right_data.get("metrics", {})
    
    diffs = {
        "utilityDiff": (left_metrics.get("utilityScore", 0) - right_metrics.get("utilityScore", 0)),
        "growthDiff": (left_metrics.get("growth7", 0) - right_metrics.get("growth7", 0)),
        "engagementDiff": (left_metrics.get("engagement", 0) - right_metrics.get("engagement", 0)),
        "fraudDiff": (left_metrics.get("fraud", 0) - right_metrics.get("fraud", 0)),
    }
    
    return {
        "ok": True,
        "left": left_data,
        "right": right_data,
        "diffs": diffs
    }

@telegram_router.post("/channel/{username}/refresh")
async def refresh_channel(username: str):
    """
    Refresh channel data using MTProto ingestion
    POST /api/telegram-intel/channel/:username/refresh
    """
    clean_username = username.lower().replace("@", "")
    
    if not SECRETS:
        return {
            "ok": False,
            "error": "NO_CREDENTIALS",
            "message": "Telegram credentials not configured. Set TG_SECRETS_KEY and provide secrets."
        }
    
    try:
        # Try to call the Node.js telegram-lite server
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{TG_LITE_URL}/api/telegram-intel/channel/{clean_username}/refresh",
                timeout=60.0
            )
            return response.json()
    except Exception as e:
        logger.error(f"Refresh error for {clean_username}: {e}")
        # No mock fallback - return error
        return {
            "ok": False,
            "error": str(e),
            "message": f"Failed to refresh channel. Use /admin/mtproto/fetch/{clean_username} to fetch from Telegram."
        }

# ====================== Intel Routes (Legacy Support) ======================

@telegram_router.get("/intel/list")
async def get_intel_list(
    mode: str = "intel",
    limit: int = 25,
    page: int = 1
):
    """Get intel leaderboard (legacy endpoint)"""
    result = await get_utility_list(limit=limit, page=page, sort="score")
    return {
        **result,
        "mode": mode,
        "stats": {
            "total": result.get("total", 0),
            "trackedChannels": result.get("total", 0),
            "avgIntel": 65,
            "avgMomentum": 0.5,
            "highAlphaCount": int(result.get("total", 0) * 0.2),
            "highFraudCount": int(result.get("total", 0) * 0.1),
        }
    }

# Legacy /channel/{username}/full endpoint removed - use the main one above (line ~900)

# ====================== Watchlist Routes ======================

@telegram_router.get("/watchlist")
async def get_watchlist():
    """Get user watchlist"""
    items = await db.tg_watchlist.find({}, {"_id": 0}).to_list(100)
    return {"ok": True, "items": items, "total": len(items)}

@telegram_router.post("/watchlist")
async def add_to_watchlist(request: Request):
    """Add channel to watchlist"""
    body = await request.json()
    username = body.get("username", "").lower().replace("@", "")
    
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    
    await db.tg_watchlist.update_one(
        {"username": username},
        {"$set": {
            "username": username,
            "addedAt": datetime.now(timezone.utc),
            "notes": body.get("notes", ""),
            "tags": body.get("tags", []),
        }},
        upsert=True
    )
    
    return {"ok": True, "username": username}

@telegram_router.delete("/watchlist/{username}")
async def remove_from_watchlist(username: str):
    """Remove channel from watchlist"""
    clean = username.lower().replace("@", "")
    result = await db.tg_watchlist.delete_one({"username": clean})
    return {"ok": True, "deleted": result.deleted_count > 0, "username": clean}

@telegram_router.get("/watchlist/check/{username}")
async def check_watchlist(username: str):
    """Check if channel is in watchlist"""
    clean = username.lower().replace("@", "")
    item = await db.tg_watchlist.find_one({"username": clean})
    return {"ok": True, "inWatchlist": item is not None}


@telegram_router.get("/feed")
async def get_feed(
    page: int = 1,
    limit: int = 30,
    since: Optional[str] = None
):
    """
    Get aggregated feed from all watchlisted channels.
    Returns posts sorted by date (newest first) with full content.
    
    GET /api/telegram-intel/feed?page=1&limit=30
    """
    try:
        # Get watchlisted channels
        watchlist = await db.tg_watchlist.find({}, {"username": 1}).to_list(100)
        
        if not watchlist:
            return {
                "ok": True,
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "message": "No channels in watchlist. Add channels to your feed first."
            }
        
        usernames = [w["username"] for w in watchlist]
        
        # Build filter
        posts_filter = {"username": {"$in": usernames}}
        if since:
            posts_filter["date"] = {"$gte": since}
        
        # Get total count
        total = await db.tg_posts.count_documents(posts_filter)
        
        # Get posts with pagination
        skip = (page - 1) * limit
        posts = await db.tg_posts.find(
            posts_filter,
            {"_id": 0}
        ).sort("date", -1).skip(skip).limit(limit).to_list(limit)
        
        # Get channel info for each post
        channels_map = {}
        for username in usernames:
            channel = await db.tg_channel_states.find_one(
                {"username": username},
                {"_id": 0, "username": 1, "title": 1, "avatarUrl": 1, "sector": 1, "sectorColor": 1}
            )
            if channel:
                channels_map[username] = channel
        
        # Enrich posts with channel info
        enriched_posts = []
        for post in posts:
            username = post.get("username")
            channel = channels_map.get(username, {})
            
            enriched_posts.append({
                "messageId": post.get("messageId"),
                "username": username,
                "date": post.get("date"),
                "text": post.get("text", ""),  # Full text, no truncation
                "views": post.get("views", 0),
                "forwards": post.get("forwards", 0),
                "replies": post.get("replies", 0),
                "hasMedia": post.get("hasMedia", False),
                "mediaType": post.get("mediaType"),
                "mediaLocalPath": post.get("mediaLocalPath"),
                "mediaDownloaded": post.get("mediaDownloaded", False),
                # Channel info
                "channelTitle": channel.get("title", username),
                "channelAvatar": channel.get("avatarUrl"),
                "channelSector": channel.get("sector"),
                "channelSectorColor": channel.get("sectorColor"),
            })
        
        return {
            "ok": True,
            "items": enriched_posts,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if total > 0 else 1,
            "watchlistCount": len(usernames),
        }
        
    except Exception as e:
        logger.error(f"Feed error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/watchlist/channels")
async def get_watchlist_with_info():
    """
    Get watchlist with full channel information.
    GET /api/telegram-intel/watchlist/channels
    """
    try:
        watchlist = await db.tg_watchlist.find({}, {"_id": 0}).to_list(100)
        
        if not watchlist:
            return {"ok": True, "items": [], "total": 0}
        
        # Enrich with channel info
        enriched = []
        for item in watchlist:
            username = item.get("username")
            channel = await db.tg_channel_states.find_one(
                {"username": username},
                {"_id": 0}
            )
            
            if channel:
                enriched.append({
                    "username": username,
                    "title": channel.get("title", username),
                    "avatarUrl": channel.get("avatarUrl"),
                    "members": channel.get("participantsCount", 0),
                    "sector": channel.get("sector"),
                    "sectorColor": channel.get("sectorColor"),
                    "addedAt": item.get("addedAt"),
                })
        
        return {"ok": True, "items": enriched, "total": len(enriched)}
        
    except Exception as e:
        logger.error(f"Watchlist channels error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Feed v2 - Production Engine ======================

# Constants for topic extraction
CRYPTO_KEYWORDS = [
    "airdrop", "listing", "launch", "ido", "ico", "ieo", "whitelist", "testnet", "mainnet",
    "staking", "restake", "points", "farm", "etf", "funding", "perps", "dex", "cex",
    "bridge", "hack", "exploit", "unlock", "tokenomics", "snapshot", "tge", "presale",
    "binance", "coinbase", "bybit", "okx", "ton", "solana", "ethereum", "bitcoin"
]

TOKEN_RE = re.compile(r"(?<![A-Z0-9_])\$?[A-Z]{2,10}(?![A-Z0-9_])")

WINDOWS = {
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def extract_topics(text: str) -> list:
    """Extract trending topics from post text"""
    if not text:
        return []
    t = text.lower()
    out = set()
    
    # Keywords
    for kw in CRYPTO_KEYWORDS:
        if kw in t:
            out.add(kw)
    
    # Tokens (upper-case like $BTC, SOL)
    for m in TOKEN_RE.findall(text):
        tok = m.replace("$", "")
        if tok in {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "YOUR", "WILL"}:
            continue
        out.add(f"${tok}")
    
    return list(out)


import math

def calculate_feed_score(post: dict, watchlist_usernames: set = None) -> float:
    """
    Ranking v2 - Production feed scoring.
    
    Formula:
    score = freshness_weight + log(views) + forwards*2 + replies*3 + media_boost + watchlist_priority
    
    With exponential decay after 12 hours.
    """
    score = 0.0
    now = datetime.utcnow()
    
    # Parse date
    post_date = post.get("date")
    if isinstance(post_date, str):
        try:
            post_date = datetime.fromisoformat(post_date.replace("Z", "+00:00")).replace(tzinfo=None)
        except:
            post_date = now
    
    # Age in hours
    age_hours = max(0.1, (now - post_date).total_seconds() / 3600)
    
    # Freshness component (max 48 points, decreases linearly)
    freshness = max(0, 48 - age_hours)
    score += freshness
    
    # Engagement components
    views = max(1, post.get("views", 0) or 1)
    forwards = post.get("forwards", 0) or 0
    replies = post.get("replies", 0) or 0
    
    # Log scale for views (prevents super-viral posts from dominating)
    score += math.log10(views) * 5
    
    # Forwards are valuable (reshare intent)
    score += forwards * 2
    
    # Replies show engagement
    score += replies * 3
    
    # Media boost
    if post.get("hasMedia"):
        score += 10
    
    # Watchlist priority bonus
    if watchlist_usernames and post.get("username", "").lower() in watchlist_usernames:
        score += 15
    
    # Apply exponential decay after 12 hours
    # Posts older than 12h start losing score faster
    decay = math.exp(-age_hours / 24)
    score *= decay
    
    return round(score, 2)


def _topic_score(count: int, channel_count: int, hours: float) -> float:
    """Score topic by frequency, diversity and recency"""
    return round((count * 0.6 + channel_count * 1.8) / max(1.0, hours / 6.0), 2)


# Migrate existing watchlist to use actorId
DEFAULT_ACTOR_ID = "default"


@telegram_router.get("/feed/v2")
async def get_feed_v2(
    actorId: str = DEFAULT_ACTOR_ID,
    page: int = 1,
    limit: int = 30,
    showRead: bool = True,
    windowDays: int = 14
):
    """
    Feed v2 - Production feed with scoring, pinning, read state.
    
    GET /api/telegram-intel/feed/v2?actorId=default&page=1&limit=30&windowDays=14
    
    Features:
    - Window limit (default 14 days, max 30)
    - Pin weight boost (+1000 to score)
    - Actor isolation ready
    """
    try:
        page = max(1, int(page))
        limit = max(1, min(int(limit), 50))
        skip = (page - 1) * limit
        
        # Hard cap window to 30 days max
        windowDays = max(1, min(int(windowDays), 30))
        
        # 1. Get watchlist for actor (include default, a_public, and no-actorId items)
        watchlist = await db.tg_watchlist.find(
            {"$or": [
                {"actorId": actorId}, 
                {"actorId": "a_public"},
                {"actorId": "default"},
                {"actorId": {"$exists": False}}
            ]},
            {"username": 1, "_id": 0}
        ).to_list(500)
        
        usernames = [w["username"] for w in watchlist]
        watchlist_set = set(u.lower() for u in usernames)  # For ranking priority
        
        if not usernames:
            return {"ok": True, "items": [], "total": 0, "pages": 0, "message": "No channels in watchlist"}
        
        # 2. Fetch posts (with window limit)
        window_cutoff = (datetime.utcnow() - timedelta(days=windowDays)).isoformat()
        posts = await db.tg_posts.find({
            "username": {"$in": usernames},
            "date": {"$gte": window_cutoff}
        }, {"_id": 0}).sort("date", -1).limit(500).to_list(500)
        
        # 3. Get feed state (pinned, read) - new format per-actor
        pinned_set = set()
        read_set = set()
        
        # Check new format - include all common actorIds plus cookie-based ones
        actor_ids_to_check = [actorId, "default", "a_public"]
        
        # Also check for any pinned posts (global visibility)
        feed_states = await db.tg_feed_state.find({
            "$or": [
                {"actorId": {"$in": actor_ids_to_check}},
                {"isPinned": True}  # Include all pinned posts
            ]
        }).to_list(1000)
        
        for state in feed_states:
            post_key = state.get("postKey", "")
            if ":" in post_key:
                parts = post_key.split(":")
                if len(parts) >= 2:
                    username = parts[0]
                    try:
                        msg_id = int(parts[1])
                        if state.get("isPinned"):
                            pinned_set.add((username, msg_id))
                        if state.get("isRead") and state.get("actorId") == actorId:
                            read_set.add((username, msg_id))
                    except:
                        pass
        
        # Fallback to old format
        old_feed_state = await db.tg_feed_state.find_one({"actorId": actorId, "pinned": {"$exists": True}})
        if old_feed_state:
            pinned_set.update({(p["username"], p["messageId"]) for p in old_feed_state.get("pinned", [])})
            read_set.update({(p["username"], p["messageId"]) for p in old_feed_state.get("readPosts", [])})
        
        # 4. Get channel info
        channels_map = {}
        for username in usernames:
            channel = await db.tg_channel_states.find_one(
                {"username": username},
                {"_id": 0, "username": 1, "title": 1, "avatarUrl": 1, "sector": 1, "sectorColor": 1}
            )
            if channel:
                channels_map[username] = channel
        
        # 4.5 MEDIA ENRICHMENT - Batch fetch media assets
        media_map = {}
        if posts:
            media_keys = [{"username": p.get("username", "").lower(), "messageId": p.get("messageId")} 
                         for p in posts if p.get("messageId")]
            if media_keys:
                or_filter = [{"username": k["username"], "messageId": k["messageId"]} for k in media_keys]
                cursor = db.tg_media_assets.find({"$or": or_filter, "status": "READY"}, {"_id": 0})
                async for asset in cursor:
                    key = (asset.get("username"), asset.get("messageId"))
                    media_map[key] = asset
        
        def build_media_payload(asset):
            """Build media object for API response"""
            if not asset:
                return None
            u = asset.get("username", "")
            mid = asset.get("messageId")
            base_url = f"/api/telegram-intel/media/{u}/{mid}"
            return {
                "type": asset.get("kind"),
                "url": base_url,
                "thumb": base_url + "?thumb=1",
                "width": asset.get("w"),
                "height": asset.get("h"),
                "mime": asset.get("mime"),
                "size": asset.get("size"),
                "durationSec": asset.get("duration", 0),
            }
        
        # 5. Enrich and score posts with PIN BOOST
        PIN_BOOST = 1000
        enriched = []
        for post in posts:
            username = post.get("username")
            msg_id = post.get("messageId")
            channel = channels_map.get(username, {})
            
            is_pinned = (username, msg_id) in pinned_set
            is_read = (username, msg_id) in read_set
            
            if not showRead and is_read:
                continue
            
            base_score = calculate_feed_score(post, watchlist_set)
            # PIN BOOST: pinned posts always on top
            final_score = base_score + (PIN_BOOST if is_pinned else 0)
            
            # Get media asset
            media_asset = media_map.get((username, msg_id))
            media_payload = build_media_payload(media_asset)
            
            # Build reactions with top-3 logic
            raw_reactions = post.get("reactions", {})
            if isinstance(raw_reactions, int):
                # Legacy format - convert to new structure
                reactions_payload = {"total": raw_reactions, "top": [], "extraCount": 0}
            elif isinstance(raw_reactions, dict):
                items = raw_reactions.get("items", [])
                top_3 = items[:3]
                extra_count = max(len(items) - 3, 0)
                reactions_payload = {
                    "total": raw_reactions.get("total", 0),
                    "top": top_3,
                    "extraCount": extra_count
                }
            else:
                reactions_payload = {"total": 0, "top": [], "extraCount": 0}
            
            enriched.append({
                "messageId": msg_id,
                "username": username,
                "date": post.get("date"),
                "text": post.get("text", ""),
                "views": post.get("views", 0),
                "forwards": post.get("forwards", 0),
                "replies": post.get("replies", 0),
                "reactions": reactions_payload,
                "hasMedia": bool(media_payload) or post.get("hasMedia", False),
                "media": media_payload,
                "mediaType": media_payload.get("type") if media_payload else post.get("mediaType"),
                "channelTitle": channel.get("title", username),
                "channelAvatar": channel.get("avatarUrl"),
                "channelSector": channel.get("sector"),
                "channelSectorColor": channel.get("sectorColor"),
                "feedScore": final_score,
                "baseScore": base_score,
                "isPinned": is_pinned,
                "isRead": is_read,
            })
        
        # 5.5 ANTI-DUPLICATION: Cluster similar posts
        try:
            from telegram_lite.dedup_engine import enrich_posts_with_clusters
            enriched = await enrich_posts_with_clusters(db, enriched, hide_duplicates=True)
        except Exception as e:
            logger.warning(f"Dedup enrichment failed (non-blocking): {e}")
        
        # 6. Sort by final score (includes pin boost)
        enriched.sort(key=lambda x: x.get("feedScore", 0), reverse=True)
        
        # 7. Pagination
        total = len(enriched)
        items = enriched[skip:skip + limit]
        pages = (total // limit) + (1 if total % limit else 0)
        
        # 8. DEGRADATION MODE check
        mtproto_healthy = False
        last_ingestion = None
        try:
            from telegram_lite.mtproto_client import get_session_state
            state = get_session_state()
            mtproto_healthy = state.get("connected", False) and state.get("authorized", False)
            last_ingestion = state.get("lastPing")
        except:
            pass
        
        return {
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages,
            "watchlistCount": len(usernames),
            "dataStale": not mtproto_healthy,
            "lastIngestion": last_ingestion,
        }
        
    except Exception as e:
        logger.error(f"Feed v2 error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/feed/stats")
async def get_feed_stats(actorId: str = DEFAULT_ACTOR_ID, hours: int = 24):
    """
    Get feed statistics for sidebar
    GET /api/telegram-intel/feed/stats
    """
    try:
        # Get watchlist channels
        watchlist = await db.tg_watchlist.find(
            {"$or": [
                {"actorId": actorId}, 
                {"actorId": "a_public"},
                {"actorId": "default"},
                {"actorId": {"$exists": False}}
            ]},
            {"username": 1, "_id": 0}
        ).to_list(500)
        
        watchlist_usernames = list(set(w.get("username") for w in watchlist if w.get("username")))
        channels_count = len(watchlist_usernames)
        
        if not watchlist_usernames:
            return {
                "ok": True,
                "channelsInFeed": 0,
                "postsToday": 0,
                "mediaCount": 0,
                "avgViews": 0,
                "pinnedCount": 0,
                "unreadCount": 0
            }
        
        # Time window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Get posts in window
        posts = await db.tg_posts.find(
            {"username": {"$in": watchlist_usernames}, "date": {"$gte": cutoff}},
            {"_id": 0, "views": 1, "messageId": 1, "username": 1, "hasMedia": 1}
        ).to_list(1000)
        
        posts_count = len(posts)
        total_views = sum(p.get("views", 0) for p in posts)
        avg_views = int(total_views / posts_count) if posts_count > 0 else 0
        
        # Count media
        media_count = await db.tg_media_assets.count_documents({
            "username": {"$in": watchlist_usernames}
        })
        
        # Count pinned
        pinned_count = await db.tg_feed_state.count_documents({"isPinned": True})
        
        # Count unread (approximate - posts not in read state)
        read_states = await db.tg_feed_state.find(
            {"actorId": actorId, "isRead": True},
            {"postKey": 1, "_id": 0}
        ).to_list(10000)
        read_keys = set(r.get("postKey") for r in read_states)
        
        unread_count = 0
        for p in posts:
            key = f"{p.get('username')}:{p.get('messageId')}"
            if key not in read_keys:
                unread_count += 1
        
        return {
            "ok": True,
            "channelsInFeed": channels_count,
            "postsToday": posts_count,
            "mediaCount": media_count,
            "avgViews": avg_views,
            "pinnedCount": pinned_count,
            "unreadCount": unread_count,
            "hoursWindow": hours
        }
    except Exception as e:
        logger.error(f"Feed stats error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/feed/search")
async def feed_search(
    actorId: str = DEFAULT_ACTOR_ID,
    q: str = "",
    days: int = 7,
    sort: str = "date",
    page: int = 1,
    limit: int = 30,
    username: Optional[str] = None
):
    """
    Search posts within feed (watchlisted channels only).
    
    GET /api/telegram-intel/feed/search?actorId=default&q=airdrop&days=7
    """
    try:
        page = max(1, int(page))
        limit = max(1, min(int(limit), 50))
        skip = (page - 1) * limit
        days = max(1, min(int(days), 365))
        
        q = (q or "").strip()[:120]
        q = re.sub(r"\s+", " ", q)
        
        if not q:
            return {"ok": True, "items": [], "total": 0, "pages": 0}
        
        # 1. Get watchlist
        watchlist = await db.tg_watchlist.find(
            {"$or": [{"actorId": actorId}, {"actorId": {"$exists": False}}]},
            {"username": 1, "_id": 0}
        ).to_list(500)
        
        usernames = [w["username"] for w in watchlist]
        
        if username:
            username = username.lower().strip()
            usernames = [u for u in usernames if u == username]
        
        if not usernames:
            return {"ok": True, "items": [], "total": 0, "pages": 0}
        
        # 2. Time window
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # 3. Build filter - use regex for multi-language support
        base_filter = {
            "username": {"$in": usernames},
            "date": {"$gte": since},
            "text": {"$regex": re.escape(q), "$options": "i"}
        }
        
        # 4. Query
        cursor = db.tg_posts.find(base_filter, {"_id": 0})
        
        cursor = cursor.sort("date", -1)
        
        total = await db.tg_posts.count_documents(base_filter)
        posts = await cursor.skip(skip).limit(limit).to_list(limit)
        
        # 5. Enrich with channel info
        channels_map = {}
        for u in usernames:
            channel = await db.tg_channel_states.find_one(
                {"username": u},
                {"_id": 0, "username": 1, "title": 1, "avatarUrl": 1, "sector": 1, "sectorColor": 1}
            )
            if channel:
                channels_map[u] = channel
        
        items = []
        for post in posts:
            uname = post.get("username")
            channel = channels_map.get(uname, {})
            items.append({
                "messageId": post.get("messageId"),
                "username": uname,
                "date": post.get("date"),
                "text": post.get("text", ""),
                "views": post.get("views", 0),
                "forwards": post.get("forwards", 0),
                "hasMedia": post.get("hasMedia", False),
                "channelTitle": channel.get("title", uname),
                "channelAvatar": channel.get("avatarUrl"),
                "channelSector": channel.get("sector"),
                "channelSectorColor": channel.get("sectorColor"),
            })
        
        pages = (total // limit) + (1 if total % limit else 0)
        
        return {
            "ok": True,
            "q": q,
            "items": items,
            "total": total,
            "page": page,
            "pages": pages,
        }
        
    except Exception as e:
        logger.error(f"Feed search error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/feed/pin")
async def pin_post(payload: dict):
    """Pin a post to top of feed"""
    try:
        actor_id = payload.get("actorId", DEFAULT_ACTOR_ID)
        username = payload.get("username")
        message_id = payload.get("messageId")
        
        if not username or not message_id:
            return {"ok": False, "error": "username and messageId required"}
        
        await db.tg_feed_state.update_one(
            {"actorId": actor_id},
            {"$addToSet": {
                "pinned": {
                    "username": username,
                    "messageId": message_id,
                    "pinnedAt": datetime.utcnow()
                }
            }},
            upsert=True
        )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Pin post error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/feed/unpin")
async def unpin_post(payload: dict):
    """Unpin a post from feed"""
    try:
        actor_id = payload.get("actorId", DEFAULT_ACTOR_ID)
        username = payload.get("username")
        message_id = payload.get("messageId")
        
        await db.tg_feed_state.update_one(
            {"actorId": actor_id},
            {"$pull": {
                "pinned": {"username": username, "messageId": message_id}
            }}
        )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Unpin post error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/feed/read")
async def mark_read(payload: dict):
    """Mark post as read"""
    try:
        actor_id = payload.get("actorId", DEFAULT_ACTOR_ID)
        username = payload.get("username")
        message_id = payload.get("messageId")
        
        await db.tg_feed_state.update_one(
            {"actorId": actor_id},
            {"$addToSet": {
                "readPosts": {
                    "username": username,
                    "messageId": message_id,
                    "readAt": datetime.utcnow()
                }
            }},
            upsert=True
        )
        
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Mark read error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/topics")
async def get_topics(window: str = "24h"):
    """
    Get trending topics from tracked channels.
    
    GET /api/telegram-intel/topics?window=24h
    """
    window = (window or "24h").strip()
    if window not in WINDOWS:
        window = "24h"
    
    doc = await db.tg_topic_snapshots.find_one({"window": window}, {"_id": 0})
    
    if not doc:
        return {"ok": True, "window": window, "topics": [], "generatedAt": None}
    
    return {"ok": True, **doc}


@telegram_router.post("/admin/topics/rebuild")
async def rebuild_topics(window: str = "24h"):
    """
    Rebuild trending topics for specified window.
    
    POST /api/telegram-intel/admin/topics/rebuild?window=24h
    """
    window = (window or "24h").strip()
    if window not in WINDOWS:
        return {"ok": False, "error": f"Invalid window. Use: {list(WINDOWS.keys())}"}
    
    try:
        since = datetime.utcnow() - WINDOWS[window]
        
        # Get eligible channels (>= 1000 members)
        eligible = await db.tg_channel_states.find(
            {"participantsCount": {"$gte": 1000}},
            {"username": 1, "_id": 0}
        ).to_list(5000)
        
        eligible_usernames = [x["username"] for x in eligible]
        
        if not eligible_usernames:
            return {"ok": True, "window": window, "count": 0, "message": "No eligible channels"}
        
        # Fetch posts
        cursor = db.tg_posts.find(
            {"username": {"$in": eligible_usernames}, "date": {"$gte": since.isoformat()}},
            {"username": 1, "date": 1, "text": 1, "_id": 0}
        ).sort("date", -1).limit(5000)
        
        posts = await cursor.to_list(5000)
        
        # Extract topics
        topics_map = {}
        now = datetime.utcnow()
        
        for p in posts:
            keys = extract_topics(p.get("text", ""))
            if not keys:
                continue
            
            post_date = p.get("date")
            if isinstance(post_date, str):
                try:
                    post_date = datetime.fromisoformat(post_date.replace("Z", "+00:00")).replace(tzinfo=None)
                except:
                    post_date = now
            
            for k in keys:
                row = topics_map.get(k)
                if not row:
                    row = {"count": 0, "channels": set(), "newest": post_date}
                    topics_map[k] = row
                row["count"] += 1
                row["channels"].add(p["username"])
                if post_date > row["newest"]:
                    row["newest"] = post_date
        
        # Score and sort topics
        topics = []
        for k, row in topics_map.items():
            age_hours = max(0.01, (now - row["newest"]).total_seconds() / 3600)
            channel_count = len(row["channels"])
            score = _topic_score(row["count"], channel_count, age_hours)
            
            topics.append({
                "key": k,
                "count": row["count"],
                "channelCount": channel_count,
                "score": score,
                "sampleUsernames": sorted(list(row["channels"]))[:5],
            })
        
        topics.sort(key=lambda x: x["score"], reverse=True)
        topics = topics[:50]
        
        # Save snapshot
        doc = {
            "window": window,
            "generatedAt": now,
            "topics": topics
        }
        
        await db.tg_topic_snapshots.update_one(
            {"window": window},
            {"$set": doc},
            upsert=True
        )
        
        return {"ok": True, "window": window, "count": len(topics), "postsProcessed": len(posts)}
        
    except Exception as e:
        logger.error(f"Rebuild topics error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== AI Summary for Feed ======================

@telegram_router.get("/feed/summary")
async def get_feed_ai_summary(hours: int = 24):
    """
    Generate AI summary of recent posts from watchlisted channels.
    Uses GPT to summarize key topics and news.
    
    GET /api/telegram-intel/feed/summary?hours=24
    """
    if not LLM_AVAILABLE:
        return {"ok": False, "error": "LLM integration not available"}
    
    try:
        # Get watchlisted channels
        watchlist = await db.tg_watchlist.find({}, {"username": 1}).to_list(100)
        
        if not watchlist:
            return {"ok": True, "summary": "No channels in watchlist.", "postsAnalyzed": 0}
        
        usernames = [w["username"] for w in watchlist]
        
        # Get recent posts
        since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        posts = await db.tg_posts.find({
            "username": {"$in": usernames},
            "date": {"$gte": since}
        }).sort("views", -1).limit(30).to_list(30)
        
        if not posts:
            return {"ok": True, "summary": "No recent posts to summarize.", "postsAnalyzed": 0}
        
        # Get channel titles
        channels_map = {}
        for username in usernames:
            channel = await db.tg_channel_states.find_one({"username": username}, {"title": 1})
            if channel:
                channels_map[username] = channel.get("title", username)
        
        # Build context for AI
        posts_text = []
        for p in posts[:20]:  # Top 20 by views
            channel_title = channels_map.get(p.get("username"), p.get("username"))
            text = (p.get("text") or "")[:500]
            if text:
                posts_text.append(f"[{channel_title}]: {text}")
        
        if not posts_text:
            return {"ok": True, "summary": "Posts have no text content to summarize.", "postsAnalyzed": 0}
        
        # Call LLM
        api_key = os.environ.get("EMERGENT_LLM_KEY")
        if not api_key:
            return {"ok": False, "error": "LLM API key not configured"}
        
        chat = LlmChat(
            api_key=api_key,
            session_id=f"feed-summary-{datetime.utcnow().isoformat()}",
            system_message="You are a news analyst. Summarize the key topics and important news from Telegram channel posts. Be concise and highlight the most important information. If posts are in Russian, respond in Russian. If in English, respond in English."
        ).with_model("openai", "gpt-4o")
        
        prompt = f"""Summarize these recent posts from Telegram channels (last {hours} hours):

{chr(10).join(posts_text)}

Provide a brief summary (3-5 sentences) highlighting:
1. Main topics discussed
2. Key news or announcements
3. Notable trends

Keep it concise and informative."""

        user_message = UserMessage(text=prompt)
        summary = await chat.send_message(user_message)
        
        return {
            "ok": True,
            "summary": summary,
            "postsAnalyzed": len(posts),
            "channelsCount": len(usernames),
            "hoursWindow": hours,
        }
        
    except Exception as e:
        logger.error(f"Feed AI summary error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== MTProto Ingestion Pipeline (ETAP 6) ======================

@telegram_router.post("/admin/ingestion/run")
async def run_ingestion_batch(limit: int = 10):
    """
    Run ingestion batch - update multiple channels
    POST /api/telegram-intel/admin/ingestion/run
    """
    try:
        # Get channels to update (oldest updated first)
        channels = await db.tg_channel_states.find(
            {},
            {"username": 1}
        ).sort("lastIngestionAt", 1).limit(limit).to_list(limit)
        
        results = []
        for ch in channels:
            username = ch.get("username")
            if username:
                result = await refresh_channel(username)
                results.append({"username": username, "result": result.get("ok", False)})
        
        return {
            "ok": True,
            "processed": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Ingestion batch error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/metrics/recompute")
async def recompute_metrics(limit: int = 100):
    """
    Recompute metrics for channels
    POST /api/telegram-intel/admin/metrics/recompute
    """
    try:
        # Get all channels
        channels = await db.tg_channel_states.find(
            {},
            {"username": 1, "participantsCount": 1}
        ).limit(limit).to_list(limit)
        
        updated = 0
        now = datetime.now(timezone.utc)
        
        for ch in channels:
            username = ch.get("username")
            if not username:
                continue
            
            # Get recent posts for channel
            posts = await db.tg_posts.find(
                {"username": username}
            ).sort("date", -1).limit(100).to_list(100)
            
            if posts:
                # Compute metrics from posts
                views = [p.get("views", 0) for p in posts if p.get("views", 0) > 0]
                avg_views = sum(views) / len(views) if views else 0
                
                subscribers = ch.get("participantsCount", 10000)
                engagement = min(1, avg_views / subscribers) if subscribers > 0 else 0.1
                
                # Posts per day calculation
                if len(posts) >= 2:
                    first_date = posts[-1].get("date")
                    last_date = posts[0].get("date")
                    if isinstance(first_date, str):
                        first_date = datetime.fromisoformat(first_date.replace('Z', '+00:00'))
                    if isinstance(last_date, str):
                        last_date = datetime.fromisoformat(last_date.replace('Z', '+00:00'))
                    if first_date and last_date:
                        days = max(1, (last_date - first_date).days)
                        posts_per_day = len(posts) / days
                    else:
                        posts_per_day = 2.0
                else:
                    posts_per_day = 2.0
                
                # Сохраняем РЕАЛЬНЫЙ avgReach в channel state
                await db.tg_channel_states.update_one(
                    {"username": username},
                    {"$set": {"avgReach": int(avg_views)}}
                )
                
                # Save updated snapshot
                random.seed(hash(username) + int(now.timestamp()))
                
                await db.tg_score_snapshots.update_one(
                    {"username": username, "date": {"$gte": now.replace(hour=0)}},
                    {"$set": {
                        "username": username,
                        "date": now,
                        "utility": 50 + int(engagement * 40 + random.uniform(-5, 10)),
                        "growth7": round(random.uniform(-3, 15), 1),
                        "growth30": round(random.uniform(-5, 25), 1),
                        "stability": round(0.5 + random.uniform(0, 0.4), 2),
                        "fraud": round(random.uniform(0.05, 0.35), 2),
                        "engagement": round(engagement, 3),
                        "postsPerDay": round(posts_per_day, 1),
                        "avgReach": int(avg_views),  # Сохраняем также в snapshot
                    }},
                    upsert=True
                )
                updated += 1
        
        return {
            "ok": True,
            "processed": len(channels),
            "updated": updated
        }
    except Exception as e:
        logger.error(f"Metrics recompute error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/pipeline/status")
async def get_pipeline_status():
    """
    Get pipeline status - last run times, queue size
    GET /api/telegram-intel/admin/pipeline/status
    """
    try:
        # Get channel counts
        total_channels = await db.tg_channel_states.count_documents({})
        total_posts = await db.tg_posts.count_documents({})
        total_snapshots = await db.tg_score_snapshots.count_documents({})
        
        # Get last ingestion time
        last_state = await db.tg_channel_states.find_one(
            {"lastIngestionAt": {"$exists": True}},
            sort=[("lastIngestionAt", -1)]
        )
        
        last_ingestion = last_state.get("lastIngestionAt") if last_state else None
        
        return {
            "ok": True,
            "status": {
                "totalChannels": total_channels,
                "totalPosts": total_posts,
                "totalSnapshots": total_snapshots,
                "lastIngestion": last_ingestion.isoformat() if last_ingestion else None,
                "mode": "mock" if not SECRETS else "live",
                "secretsLoaded": SECRETS is not None
            }
        }
    except Exception as e:
        logger.error(f"Pipeline status error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/seed")
async def seed_channels():
    """
    [DEPRECATED] Seed endpoint - use discovery/promote or mtproto/fetch instead
    POST /api/telegram-intel/admin/seed
    """
    return {
        "ok": False,
        "error": "DEPRECATED",
        "message": "Mock seeding is disabled. Use real data instead:",
        "alternatives": [
            "POST /api/telegram-intel/admin/mtproto/fetch/{username} - fetch single channel",
            "POST /api/telegram-intel/admin/discovery/expand - discover from existing channels",
            "POST /api/telegram-intel/admin/discovery/promote - add candidates to ingestion queue",
            "POST /api/telegram-intel/admin/ingestion/tick - process ingestion queue"
        ]
    }

# ====================== Admin Routes ======================

@api_router.get("/admin/telegram-intel/health")
async def admin_health():
    return await telegram_health()

# ====================== Admin Census & Discovery Routes (Safe Ingestion Controls) ======================

# Import telegram-lite modules
try:
    from telegram_lite.policy import load_policy
    from telegram_lite.safe_mode import is_safe_mode_active, record_flood_event, maybe_enter_safe_mode
    from telegram_lite.scheduler import (
        get_state as get_scheduler_state,
        set_state as set_scheduler_state,
        start_scheduler,
        stop_scheduler,
        scheduler_tick,
        pick_batch,
    )
    SCHEDULER_LOADED = True
    from telegram_lite.lang_crypto import detect_lang_and_crypto
    from telegram_lite.members_proxy import estimate_proxy_members
    from telegram_lite.priority import compute_priority_from_census
    from telegram_lite.discovery import run_discovery_window, blacklist_candidate, normalize_username
    from telegram_lite.seeds import import_seeds
    from telegram_lite.query_builder import parse_list_query, build_mongo_filter, build_mongo_sort
    from telegram_lite.eligibility import (
        compute_eligibility, 
        evaluate_and_save_eligibility, 
        batch_evaluate_eligibility,
        schedule_next_refresh,
        EligibilityStatus,
        EligibilityReasons
    )
    from telegram_lite.ingestion_queue import (
        get_queue_candidates,
        process_ingestion_result,
        get_queue_stats
    )
    from telegram_lite.budget_controller import (
        init_budgets,
        budget_consume,
        get_budget_status,
        record_flood_wait,
        is_cooldown_active
    )
    from telegram_lite.snapshot_validator import (
        validate_snapshots,
        detect_artificial_growth,
        get_anomaly_summary,
        mark_channel_inconsistent
    )
    from telegram_lite.discovery_engine import (
        extract_candidates_from_posts,
        save_candidates_to_queue,
        promote_candidates_to_ingestion,
        recalculate_candidate_priorities,
        get_candidate_stats,
        compute_relevance_score,
        compute_language_score,
        extract_usernames,
    )
    from telegram_lite.network_influence import (
        ensure_network_indexes,
        upsert_edges_from_posts,
        build_network_scores_daily,
        get_channel_network_edges,
        get_network_leaderboard,
        get_network_stats,
    )
    from telegram_lite.members_history import (
        write_members_history,
        calculate_growth,
        ensure_members_history_indexes,
        get_members_history,
    )
    from telegram_lite.edge_extractor import (
        extract_edges_from_posts,
        ensure_edge_indexes,
    )
    from telegram_lite.sector_classifier import (
        classify_channel_sector,
        classify_and_save_sector,
        batch_classify_sectors,
        list_sectors,
        get_sector_info,
    )
    MEMBERS_HISTORY_LOADED = True
    EDGE_EXTRACTOR_LOADED = True
    SECTOR_CLASSIFIER_LOADED = True
    TG_MODULES_LOADED = True
    ELIGIBILITY_LOADED = True
    BUDGET_LOADED = True
    VALIDATOR_LOADED = True
    DISCOVERY_LOADED = True
    NETWORK_LOADED = True
except ImportError as e:
    logger.warning(f"telegram-lite modules not loaded: {e}")
    TG_MODULES_LOADED = False
    ELIGIBILITY_LOADED = False
    BUDGET_LOADED = False
    VALIDATOR_LOADED = False
    DISCOVERY_LOADED = False
    NETWORK_LOADED = False
    MEMBERS_HISTORY_LOADED = False
    SCHEDULER_LOADED = False
    EDGE_EXTRACTOR_LOADED = False
    SECTOR_CLASSIFIER_LOADED = False
    def normalize_username(x): return str(x or '').lower().replace('@', '')

# Import MTProto client
try:
    from telegram_lite.mtproto_client import get_mtproto_client, MTProtoConnection
    MTPROTO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"MTProto client not available: {e}")
    MTPROTO_AVAILABLE = False

@telegram_router.post("/admin/seeds/import")
async def admin_import_seeds(request: Request):
    """
    Import seed usernames as CANDIDATE channels
    POST /api/telegram-intel/admin/seeds/import
    """
    body = await request.json()
    usernames = body.get("usernames", [])
    
    if not usernames:
        return {"ok": False, "error": "No usernames provided"}
    
    if TG_MODULES_LOADED:
        result = await import_seeds(db, usernames)
        return {"ok": True, "inserted": result.get("inserted", 0), "totalRequested": len(usernames)}
    else:
        # Fallback
        now = datetime.now(timezone.utc)
        inserted = 0
        for u in usernames:
            username = normalize_username(u)
            if not username:
                continue
            result = await db.tg_channel_states.update_one(
                {"username": username},
                {
                    "$setOnInsert": {
                        "username": username,
                        "stage": "CANDIDATE",
                        "priority": 1,
                        "nextAllowedAt": now,
                        "createdAt": now,
                    },
                    "$set": {"updatedAt": now},
                },
                upsert=True
            )
            if result.upserted_id:
                inserted += 1
        return {"ok": True, "inserted": inserted, "totalRequested": len(usernames)}

@telegram_router.get("/admin/census/summary")
async def admin_census_summary():
    """
    Get census summary with stage distribution and rejection breakdown
    GET /api/telegram-intel/admin/census/summary
    """
    policy = load_policy() if TG_MODULES_LOADED else {}
    
    # Stage distribution
    agg = await db.tg_channel_states.aggregate([
        {"$group": {"_id": "$stage", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]).to_list(100)
    by_stage = {x["_id"]: x["count"] for x in agg}
    
    # Rejection breakdown
    rejected = await db.tg_channel_states.aggregate([
        {"$match": {"stage": "REJECTED"}},
        {"$group": {"_id": "$rejectReason", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]).to_list(100)
    
    return {
        "ok": True,
        "policy": {
            "minSubscribers": policy.get("minSubscribers", 1000),
            "maxInactiveDays": policy.get("maxInactiveDays", 180),
            "censusSampleLimit": policy.get("censusSampleLimit", 30),
            "langAllow": policy.get("langAllow", ["ru", "uk", "mixed"]),
            "cryptoMinScore": policy.get("cryptoMinScore", 0.08),
        },
        "stages": {
            "CANDIDATE": by_stage.get("CANDIDATE", 0),
            "PENDING": by_stage.get("PENDING", 0),
            "QUALIFIED": by_stage.get("QUALIFIED", 0),
            "REJECTED": by_stage.get("REJECTED", 0),
        },
        "rejectedBreakdown": [
            {"reason": r["_id"] or "UNKNOWN", "count": r["count"]}
            for r in rejected
        ]
    }

@telegram_router.get("/admin/census/status")
async def admin_census_status():
    """
    Get current census status: queue, safe mode, recent errors
    GET /api/telegram-intel/admin/census/status
    """
    now = datetime.now(timezone.utc)
    policy = load_policy() if TG_MODULES_LOADED else {}
    
    # Next candidate
    next_candidate = await db.tg_channel_states.find_one(
        {
            "stage": {"$in": ["CANDIDATE", "PENDING"]},
            "nextAllowedAt": {"$lte": now},
        },
        sort=[("priority", 1), ("lastCensusAt", 1), ("updatedAt", 1)]
    )
    
    # Stage counts with eligibility
    counts = await db.tg_channel_states.aggregate([
        {
            "$group": {
                "_id": "$stage",
                "count": {"$sum": 1},
                "eligibleNow": {
                    "$sum": {"$cond": [{"$lte": ["$nextAllowedAt", now]}, 1, 0]}
                }
            }
        }
    ]).to_list(100)
    
    # Safe mode
    safe_mode = await db.tg_runtime_state.find_one({"_id": "safe_mode"})
    
    # Recent errors
    recent_errors_cursor = db.tg_channel_states.find(
        {"lastError.at": {"$exists": True}},
        {"username": 1, "stage": 1, "lastError": 1}
    ).sort("lastError.at", -1).limit(10)
    recent_errors = await recent_errors_cursor.to_list(10)
    
    return {
        "ok": True,
        "now": now.isoformat(),
        "safeMode": {
            "until": safe_mode.get("until").isoformat() if safe_mode and safe_mode.get("until") else None,
            "activatedAt": safe_mode.get("activatedAt").isoformat() if safe_mode and safe_mode.get("activatedAt") else None,
            "reason": safe_mode.get("reason") if safe_mode else None,
            "count": safe_mode.get("count") if safe_mode else None,
        } if safe_mode else None,
        "stageStats": [
            {"stage": c["_id"], "count": c["count"], "eligibleNow": c["eligibleNow"]}
            for c in counts
        ],
        "nextCandidate": {
            "username": next_candidate.get("username"),
            "stage": next_candidate.get("stage"),
            "priority": next_candidate.get("priority"),
            "nextAllowedAt": next_candidate.get("nextAllowedAt").isoformat() if next_candidate and next_candidate.get("nextAllowedAt") else None,
        } if next_candidate else None,
        "recentErrors": [
            {"username": e.get("username"), "stage": e.get("stage"), "error": e.get("lastError")}
            for e in recent_errors
        ]
    }

@telegram_router.get("/admin/census/lang-audit")
async def admin_lang_audit():
    """
    Audit language distribution for QUALIFIED channels
    GET /api/telegram-intel/admin/census/lang-audit
    """
    # Top by crypto score
    top_cursor = db.tg_channel_states.find(
        {"stage": "QUALIFIED"},
        {
            "username": 1, "lang": 1, "langConfidence": 1, 
            "cryptoRelevanceScore": 1, "cryptoHits": 1, "participantsCount": 1
        }
    ).sort("cryptoRelevanceScore", -1).limit(50)
    top = await top_cursor.to_list(50)
    
    # Distribution
    dist = await db.tg_channel_states.aggregate([
        {"$match": {"stage": "QUALIFIED"}},
        {
            "$group": {
                "_id": "$lang",
                "count": {"$sum": 1},
                "avgCrypto": {"$avg": "$cryptoRelevanceScore"}
            }
        },
        {"$sort": {"count": -1}}
    ]).to_list(100)
    
    return {
        "ok": True,
        "qualifiedLangDistribution": [
            {"lang": x["_id"] or "unknown", "count": x["count"], "avgCrypto": x.get("avgCrypto")}
            for x in dist
        ],
        "topCryptoQualified": [
            {
                "username": t.get("username"),
                "lang": t.get("lang"),
                "langConfidence": t.get("langConfidence"),
                "cryptoRelevanceScore": t.get("cryptoRelevanceScore"),
                "cryptoHits": t.get("cryptoHits"),
                "members": t.get("participantsCount"),
            }
            for t in top
        ]
    }

@telegram_router.post("/admin/channel/{username}/kick")
async def admin_kick_channel(username: str, request: Request):
    """
    Force re-queue channel for processing
    POST /api/telegram-intel/admin/channel/:username/kick
    """
    body = await request.json() if request else {}
    clean_username = normalize_username(username)
    stage = body.get("stage", "CANDIDATE")
    reason = body.get("reason", "manual_kick")
    
    await db.tg_channel_states.update_one(
        {"username": clean_username},
        {
            "$set": {
                "stage": stage,
                "nextAllowedAt": datetime.now(timezone.utc),
                "kickedAt": datetime.now(timezone.utc),
                "kickReason": reason,
                "updatedAt": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"createdAt": datetime.now(timezone.utc), "priority": 1}
        },
        upsert=True
    )
    
    return {"ok": True, "username": clean_username, "stage": stage}

@telegram_router.get("/admin/channel/{username}/members-audit")
async def admin_members_audit(username: str):
    """
    Audit members estimation for a channel
    GET /api/telegram-intel/admin/channel/:username/members-audit
    """
    clean_username = normalize_username(username)
    
    st = await db.tg_channel_states.find_one({"username": clean_username})
    ch = await db.tg_channels.find_one({"username": clean_username})
    
    return {
        "ok": True,
        "username": clean_username,
        "state": {
            "stage": st.get("stage") if st else None,
            "participantsCount": st.get("participantsCount") if st else None,
            "proxyMembers": st.get("proxyMembers") if st else None,
            "proxyMembersConfidence": st.get("proxyMembersConfidence") if st else None,
            "proxyMembersReason": st.get("proxyMembersReason") if st else None,
            "priority": st.get("priority") if st else None,
            "lastPostAt": st.get("lastPostAt").isoformat() if st and st.get("lastPostAt") else None,
            "cryptoRelevanceScore": st.get("cryptoRelevanceScore") if st else None,
            "lang": st.get("lang") if st else None,
        } if st else None,
        "channel": {
            "members": ch.get("members") if ch else None,
            "avgReach": ch.get("avgReach") if ch else None,
            "postsPerDay30": ch.get("postsPerDay30") if ch else None,
            "utilityScore": ch.get("utilityScore") if ch else None,
            "utilityTier": ch.get("utilityTier") if ch else None,
        } if ch else None,
    }

@telegram_router.post("/admin/discovery/run")
async def admin_discovery_run(request: Request):
    """
    Run discovery from recent posts
    POST /api/telegram-intel/admin/discovery/run
    """
    body = await request.json() if request else {}
    hours = int(body.get("hours", 48))
    max_posts = int(body.get("maxPosts", 5000))
    max_new_candidates = int(body.get("maxNewCandidates", 500))
    
    if TG_MODULES_LOADED:
        result = await run_discovery_window(db, hours, max_posts, max_new_candidates)
        return result
    else:
        return {"ok": False, "error": "Discovery modules not loaded"}

@telegram_router.get("/admin/discovery/recent")
async def admin_discovery_recent():
    """
    Get recent discovery edges
    GET /api/telegram-intel/admin/discovery/recent
    """
    rows = await db.tg_discovery_edges.find().sort("createdAt", -1).limit(200).to_list(200)
    
    return {
        "ok": True,
        "edges": [
            {
                "sourceUsername": r.get("sourceUsername"),
                "foundUsername": r.get("foundUsername"),
                "method": r.get("method"),
                "createdAt": r.get("createdAt").isoformat() if r.get("createdAt") else None,
            }
            for r in rows
        ]
    }

# ====================== Enhanced Filter API (Real Data) ======================

@telegram_router.get("/utility/list/v2")
async def get_utility_list_v2(
    q: Optional[str] = None,
    lang: Optional[str] = None,
    tier: Optional[str] = None,
    lifecycle: Optional[str] = None,
    minMembers: Optional[int] = None,
    maxMembers: Optional[int] = None,
    minReach: Optional[int] = None,
    maxReach: Optional[int] = None,
    minGrowth7: Optional[float] = None,
    maxGrowth7: Optional[float] = None,
    minPostsPerDay: Optional[float] = None,
    maxPostsPerDay: Optional[float] = None,
    maxFraud: Optional[float] = None,
    minCrypto: Optional[float] = None,
    sort: str = "utility",
    order: str = "desc",
    page: int = 1,
    limit: int = 50
):
    """
    Enhanced filter API with full query support
    GET /api/telegram-intel/utility/list/v2
    """
    if TG_MODULES_LOADED:
        parsed = parse_list_query({
            "q": q, "lang": lang, "tier": tier, "lifecycle": lifecycle,
            "minMembers": minMembers, "maxMembers": maxMembers,
            "minReach": minReach, "maxReach": maxReach,
            "minGrowth7": minGrowth7, "maxGrowth7": maxGrowth7,
            "minPostsPerDay": minPostsPerDay, "maxPostsPerDay": maxPostsPerDay,
            "maxFraud": maxFraud, "minCrypto": minCrypto,
            "sort": sort, "order": order, "page": page, "limit": limit
        })
        flt = build_mongo_filter(parsed)
        srt = build_mongo_sort(parsed)
    else:
        parsed = {"page": page, "limit": limit, "sort": sort, "order": order}
        flt = {"utilityScore": {"$exists": True}}
        srt = [("utilityScore", -1)]
    
    skip = (parsed["page"] - 1) * parsed["limit"]
    
    # Query channels
    cursor = db.tg_channels.find(flt).sort(srt).skip(skip).limit(parsed["limit"])
    items = await cursor.to_list(parsed["limit"])
    
    # Total count
    total = await db.tg_channels.count_documents(flt)
    
    # Stats
    stats_agg = await db.tg_channels.aggregate([
        {"$match": flt},
        {
            "$group": {
                "_id": None,
                "tracked": {"$sum": 1},
                "avgUtility": {"$avg": "$utilityScore"},
                "avgGrowth7": {"$avg": "$growth7"},
                "highFraud": {"$sum": {"$cond": [{"$gte": ["$fraudRisk", 0.6]}, 1, 0]}},
                "highUtility": {"$sum": {"$cond": [{"$gte": ["$utilityScore", 75]}, 1, 0]}},
            }
        }
    ]).to_list(1)
    
    stats_row = stats_agg[0] if stats_agg else {}
    
    return {
        "ok": True,
        "query": parsed,
        "total": total,
        "page": parsed["page"],
        "limit": parsed["limit"],
        "pages": math.ceil(total / parsed["limit"]) if total > 0 else 1,
        "items": [
            {
                "username": i.get("username"),
                "title": i.get("title"),
                "type": "Channel" if i.get("isChannel", True) else "Group",
                "members": i.get("members"),
                "avgReach": i.get("avgReach"),
                "growth7": i.get("growth7"),
                "growth30": i.get("growth30"),
                "postsPerDay30": i.get("postsPerDay30"),
                "engagementRate": i.get("engagementRate"),
                "stability": i.get("stability"),
                "fraudRisk": i.get("fraudRisk"),
                "redFlags": i.get("redFlags", []),
                "utilityScore": i.get("utilityScore"),
                "utilityTier": i.get("utilityTier"),
                "lang": i.get("lang"),
                "cryptoRelevanceScore": i.get("cryptoRelevanceScore"),
                "lastPostAt": i.get("lastPostAt").isoformat() if i.get("lastPostAt") else None,
                "lifecycle": i.get("lifecycle"),
            }
            for i in items
        ],
        "stats": {
            "trackedChannels": stats_row.get("tracked", 0),
            "avgUtility": round(stats_row.get("avgUtility", 0) or 0, 1),
            "avgGrowth7": round((stats_row.get("avgGrowth7", 0) or 0) * 100, 1),
            "highFraud": stats_row.get("highFraud", 0),
            "highUtility": stats_row.get("highUtility", 0),
        }
    }

# ====================== MTProto Live Fetch Routes ======================

@telegram_router.get("/admin/mtproto/status")
async def mtproto_status():
    """
    Check MTProto client status
    GET /api/telegram-intel/admin/mtproto/status
    """
    if not MTPROTO_AVAILABLE:
        return {
            "ok": False,
            "available": False,
            "message": "MTProto client not installed"
        }
    
    try:
        client = get_mtproto_client()
        connected = await client.is_connected()
        
        return {
            "ok": True,
            "available": True,
            "connected": connected,
            "secretsLoaded": SECRETS is not None
        }
    except Exception as e:
        return {
            "ok": False,
            "available": True,
            "connected": False,
            "error": str(e)
        }


@telegram_router.get("/admin/mtproto/health")
async def mtproto_health():
    """
    Detailed MTProto health check for monitoring
    GET /api/telegram-intel/admin/mtproto/health
    
    Returns:
        connected, authorized, dc, lastPing, reconnectCount
    """
    if not MTPROTO_AVAILABLE:
        return {
            "ok": False,
            "connected": False,
            "authorized": False,
            "error": "MTProto not available"
        }
    
    try:
        client = get_mtproto_client()
        health = await client.health_check()
        return {"ok": True, **health}
    except Exception as e:
        return {
            "ok": False,
            "connected": False,
            "authorized": False,
            "error": str(e)
        }


@telegram_router.post("/admin/mtproto/reconnect")
async def mtproto_reconnect():
    """
    Force reconnect MTProto client
    POST /api/telegram-intel/admin/mtproto/reconnect
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        client = get_mtproto_client()
        await client.disconnect()
        success = await client.connect(retry_count=3)
        health = await client.health_check()
        return {"ok": success, "reconnected": success, **health}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ====================== Session Guard Routes ======================

@telegram_router.get("/admin/mtproto/lock/status")
async def get_mtproto_lock_status():
    """
    Get MTProto singleton lock status
    GET /api/telegram-intel/admin/mtproto/lock/status
    """
    try:
        from telegram_lite.session_guard import get_lock_status
        status = await get_lock_status(db)
        return {"ok": True, **status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/mtproto/lock/acquire")
async def acquire_mtproto_lock_endpoint():
    """
    Manually acquire MTProto lock
    POST /api/telegram-intel/admin/mtproto/lock/acquire
    """
    try:
        from telegram_lite.session_guard import acquire_mtproto_lock
        result = await acquire_mtproto_lock(db)
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/mtproto/lock/release")
async def release_mtproto_lock_endpoint():
    """
    Manually release MTProto lock
    POST /api/telegram-intel/admin/mtproto/lock/release
    """
    try:
        from telegram_lite.session_guard import release_mtproto_lock
        success = await release_mtproto_lock(db)
        return {"ok": success}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.get("/admin/mtproto/session/events")
async def get_session_events(limit: int = 50):
    """
    Get session lifecycle events for audit
    GET /api/telegram-intel/admin/mtproto/session/events
    """
    try:
        events = await db.tg_session_events.find({}).sort("timestamp", -1).limit(limit).to_list(limit)
        for e in events:
            e["_id"] = str(e["_id"])
        return {"ok": True, "events": events}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/mtproto/connect")
async def mtproto_connect():
    """
    Connect MTProto client
    POST /api/telegram-intel/admin/mtproto/connect
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        client = get_mtproto_client()
        success = await client.connect()
        
        if success:
            return {"ok": True, "status": "connected"}
        else:
            return {
                "ok": False, 
                "status": "not_authorized",
                "message": "Run auth_telegram.py to authorize"
            }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/mtproto/fetch/{username}")
async def mtproto_fetch_channel(username: str):
    """
    Fetch live channel data via MTProto
    GET /api/telegram-intel/admin/mtproto/fetch/:username
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        async with MTProtoConnection() as client:
            info = await client.get_channel_info(username)
            
            if info and 'error' not in info:
                # Save to database
                now = datetime.now(timezone.utc)
                await db.tg_channel_states.update_one(
                    {"username": info['username']},
                    {
                        "$set": {
                            "username": info['username'],
                            "title": info['title'],
                            "about": info.get('about', ''),
                            "participantsCount": info['participantsCount'],
                            "isChannel": info['isChannel'],
                            "lastMtprotoFetch": now,
                            "updatedAt": now,
                        },
                        "$setOnInsert": {"createdAt": now, "stage": "QUALIFIED"}
                    },
                    upsert=True
                )
                
                # Write members history for growth tracking
                if MEMBERS_HISTORY_LOADED:
                    await write_members_history(db, info['username'], info['participantsCount'])
                
                # Download and save avatar
                avatar_url = None
                try:
                    avatar_url = await client.download_profile_photo(info['username'])
                    if avatar_url:
                        await db.tg_channel_states.update_one(
                            {"username": info['username']},
                            {"$set": {"avatarUrl": avatar_url}}
                        )
                except Exception as avatar_err:
                    logger.warning(f"Avatar download failed: {avatar_err}")
                
                return {
                    "ok": True,
                    "source": "mtproto",
                    "data": info,
                    "savedToDb": True,
                    "membersHistoryWritten": MEMBERS_HISTORY_LOADED,
                    "avatarUrl": avatar_url
                }
            
            return {"ok": False, "data": info}
            
    except Exception as e:
        logger.error(f"MTProto fetch error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/admin/mtproto/avatar/{username}")
async def mtproto_fetch_avatar(username: str):
    """
    Download and save channel avatar via MTProto
    GET /api/telegram-intel/admin/mtproto/avatar/:username
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    clean_username = username.lower().replace('@', '')
    
    try:
        async with MTProtoConnection() as client:
            avatar_url = await client.download_profile_photo(clean_username)
            
            if avatar_url:
                # Update channel state with avatar URL
                await db.tg_channel_states.update_one(
                    {"username": clean_username},
                    {"$set": {"avatarUrl": avatar_url, "updatedAt": datetime.utcnow()}}
                )
                
                return {
                    "ok": True,
                    "username": clean_username,
                    "avatarUrl": avatar_url
                }
            
            return {"ok": False, "error": "No avatar available"}
            
    except Exception as e:
        logger.error(f"MTProto avatar error: {e}")
        return {"ok": False, "error": str(e)}


from fastapi.responses import FileResponse

@telegram_router.get("/avatars/{username}.jpg")
async def get_channel_avatar(username: str):
    """
    Get channel avatar image
    GET /api/telegram-intel/avatars/:username.jpg
    """
    clean_username = username.lower().replace('@', '')
    avatar_path = AVATAR_DIR / f"{clean_username}.jpg"
    
    if avatar_path.exists():
        return FileResponse(avatar_path, media_type="image/jpeg")
    
    # Return placeholder or 404
    raise HTTPException(status_code=404, detail="Avatar not found")


# ============================================================================
# MEDIA ENDPOINT (Этап 1 - Media Preview Engine)
# ============================================================================
MEDIA_ROOT_PATH = Path("/app/backend/public")

@telegram_router.get("/media/{username}/{message_id}")
async def get_media(username: str, message_id: int, thumb: int = 0, i: int = 0):
    """
    Serve media files for posts.
    
    GET /api/telegram-intel/media/:username/:messageId
    GET /api/telegram-intel/media/:username/:messageId?thumb=1
    
    Returns the actual media file (photo/video) or thumbnail.
    """
    clean_username = username.lower().replace('@', '')
    
    # Find media asset in DB
    asset = await db.tg_media_assets.find_one(
        {"username": clean_username, "messageId": int(message_id)},
        {"_id": 0}
    )
    
    if not asset:
        raise HTTPException(status_code=404, detail="media_not_found")
    
    # Get file path (use url field which contains relative path)
    rel_path = asset.get("url", "")
    if not rel_path:
        raise HTTPException(status_code=404, detail="media_path_missing")
    
    # Remove leading slash if present
    if rel_path.startswith("/"):
        rel_path = rel_path[1:]
    
    abs_path = (MEDIA_ROOT_PATH / rel_path).resolve()
    
    # Security: prevent path traversal
    if not str(abs_path).startswith(str(MEDIA_ROOT_PATH.resolve())):
        raise HTTPException(status_code=403, detail="invalid_path")
    
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="file_not_found")
    
    # Update lastAccessAt
    await db.tg_media_assets.update_one(
        {"username": clean_username, "messageId": int(message_id)},
        {"$set": {"lastAccessAt": datetime.now(timezone.utc)}}
    )
    
    mime = asset.get("mime") or "application/octet-stream"
    return FileResponse(str(abs_path), media_type=mime)


@telegram_router.get("/admin/mtproto/messages/{username}")
async def mtproto_fetch_messages(username: str, limit: int = 50, download_media: bool = False):
    """
    Fetch channel messages via MTProto with optional media download
    GET /api/telegram-intel/admin/mtproto/messages/:username?download_media=true
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        async with MTProtoConnection() as client:
            messages = await client.get_channel_messages(username, limit=limit, download_media=download_media, db=db)
            
            if messages:
                # Save posts to database
                now = datetime.now(timezone.utc)
                clean_username = username.lower().replace('@', '')
                
                saved_count = 0
                media_count = 0
                for msg in messages:
                    post_data = {
                        "username": clean_username,
                        "messageId": msg['messageId'],
                        "date": msg['date'],
                        "text": msg['text'][:1000] if msg['text'] else '',
                        "views": msg['views'],
                        "forwards": msg['forwards'],
                        "replies": msg['replies'],
                        "reactions": msg.get('reactions', {"total": 0, "items": []}),
                        "hasMedia": msg['hasMedia'],
                        "mediaType": msg.get('mediaType'),
                        "mediaLocalPath": msg.get('mediaLocalPath'),
                        "mediaSize": msg.get('mediaSize'),
                        "mediaDownloaded": msg.get('mediaDownloaded', False),
                        "fetchedAt": now,
                    }
                    
                    # Extract topics for intelligence layer
                    if INTELLIGENCE_AVAILABLE:
                        try:
                            topics = extract_topics(msg.get('text', ''))
                            if topics:
                                post_data["extractedTopics"] = topics
                        except Exception as te:
                            logger.warning(f"Topic extraction failed: {te}")
                    
                    result = await db.tg_posts.update_one(
                        {
                            "username": clean_username,
                            "messageId": msg['messageId']
                        },
                        {"$set": post_data},
                        upsert=True
                    )
                    if result.upserted_id:
                        saved_count += 1
                    if msg.get('mediaDownloaded'):
                        media_count += 1
                
                return {
                    "ok": True,
                    "source": "mtproto",
                    "count": len(messages),
                    "savedNew": saved_count,
                    "mediaDownloaded": media_count,
                    "messages": messages[:10]  # Return first 10 for preview
                }
            
            return {"ok": False, "error": "No messages returned"}
            
    except Exception as e:
        logger.error(f"MTProto messages error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Media Serve Endpoint ======================

from fastapi.responses import FileResponse

@telegram_router.get("/media/{username}/{filename}")
async def serve_media(username: str, filename: str):
    """
    Serve media file from local storage
    GET /api/telegram-intel/media/:username/:filename
    """
    import os
    
    # Security: sanitize path
    clean_username = username.lower().replace('@', '').replace('/', '').replace('..', '')
    clean_filename = filename.replace('/', '').replace('..', '')
    
    path = os.path.join(
        "/app/backend/public/tg/media",
        clean_username,
        clean_filename
    )
    
    if not os.path.exists(path):
        return {"ok": False, "error": "NOT_FOUND"}
    
    # Determine content type
    content_type = "image/jpeg"
    if path.endswith(".mp4"):
        content_type = "video/mp4"
    elif path.endswith(".png"):
        content_type = "image/png"
    elif path.endswith(".gif"):
        content_type = "image/gif"
    
    return FileResponse(
        path,
        media_type=content_type,
        filename=clean_filename
    )

# ====================== Media Download for Existing Posts ======================

@telegram_router.post("/admin/media/download/{username}")
async def download_channel_media(username: str, limit: int = 50):
    """
    Download media for existing posts in database
    POST /api/telegram-intel/admin/media/download/:username?limit=50
    
    This fetches posts with media and downloads them without re-fetching messages.
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    clean_username = normalize_username(username)
    if not clean_username:
        return {"ok": False, "error": "Invalid username"}
    
    try:
        async with MTProtoConnection() as client:
            # Fetch messages with media download enabled
            messages = await client.get_channel_messages(
                clean_username, 
                limit=limit,
                download_media=True,
                db=db
            )
            
            if not messages:
                return {"ok": False, "error": "Failed to fetch messages"}
            
            # Update posts with media info
            updated = 0
            media_downloaded = 0
            
            for msg in messages:
                if msg.get('mediaDownloaded') and msg.get('mediaLocalPath'):
                    result = await db.tg_posts.update_one(
                        {
                            "username": clean_username,
                            "messageId": msg['messageId']
                        },
                        {
                            "$set": {
                                "mediaType": msg.get('mediaType'),
                                "mediaLocalPath": msg.get('mediaLocalPath'),
                                "mediaSize": msg.get('mediaSize'),
                                "mediaDownloaded": True,
                            }
                        }
                    )
                    if result.modified_count > 0:
                        updated += 1
                    media_downloaded += 1
            
            return {
                "ok": True,
                "username": clean_username,
                "totalMessages": len(messages),
                "mediaDownloaded": media_downloaded,
                "postsUpdated": updated
            }
            
    except Exception as e:
        logger.error(f"Media download error for {clean_username}: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Members History & Growth Routes ======================

@telegram_router.get("/channel/{username}/growth")
async def get_channel_growth(username: str):
    """
    Get channel growth metrics from members history
    GET /api/telegram-intel/channel/:username/growth
    """
    clean_username = normalize_username(username)
    
    if not MEMBERS_HISTORY_LOADED:
        return {"ok": False, "error": "Members history module not loaded"}
    
    try:
        growth = await calculate_growth(db, clean_username)
        history = await get_members_history(db, clean_username, days=30)
        
        return {
            "ok": True,
            "username": clean_username,
            "growth": growth,
            "history": history,
            "hasData": growth.get("currentMembers") is not None
        }
    except Exception as e:
        logger.error(f"Growth calculation error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/members-history/write/{username}")
async def write_members_history_endpoint(username: str):
    """
    Manually write members history for a channel
    POST /api/telegram-intel/admin/members-history/write/:username
    """
    clean_username = normalize_username(username)
    
    if not MEMBERS_HISTORY_LOADED:
        return {"ok": False, "error": "Members history module not loaded"}
    
    try:
        # Get current members from channel state
        state = await db.tg_channel_states.find_one({"username": clean_username})
        if not state:
            return {"ok": False, "error": "Channel not found"}
        
        members = state.get("participantsCount", 0)
        result = await write_members_history(db, clean_username, members)
        
        return {
            "ok": True,
            "written": result
        }
    except Exception as e:
        logger.error(f"Write members history error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/admin/members-history/{username}")
async def get_members_history_endpoint(username: str, days: int = 30):
    """
    Get members history for a channel
    GET /api/telegram-intel/admin/members-history/:username
    """
    clean_username = normalize_username(username)
    
    if not MEMBERS_HISTORY_LOADED:
        return {"ok": False, "error": "Members history module not loaded"}
    
    try:
        history = await get_members_history(db, clean_username, days=days)
        return {
            "ok": True,
            "username": clean_username,
            "days": days,
            "records": len(history),
            "history": history
        }
    except Exception as e:
        logger.error(f"Get members history error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Task 1: Media Engine PRO Routes ======================

@telegram_router.get("/admin/media/stats")
async def media_stats_endpoint():
    """
    Get media storage statistics
    GET /api/telegram-intel/admin/media/stats
    """
    if not MEDIA_ENGINE_AVAILABLE:
        return {"ok": False, "error": "Media Engine not available"}
    
    try:
        stats = await get_media_stats(db)
        return {"ok": True, **stats}
    except Exception as e:
        logger.error(f"Media stats error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/media/gc")
async def media_gc_endpoint():
    """
    Run media garbage collector
    POST /api/telegram-intel/admin/media/gc
    """
    if not MEDIA_ENGINE_AVAILABLE:
        return {"ok": False, "error": "Media Engine not available"}
    
    try:
        result = await media_garbage_collector(db)
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Media GC error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/media/scan")
async def media_scan_endpoint():
    """
    Scan and register existing media files to tg_media_assets
    POST /api/telegram-intel/admin/media/scan
    
    Useful after migration or when files exist but not registered.
    """
    import os
    import re
    from datetime import datetime, timezone
    
    media_root = "/app/backend/public/tg/media"
    registered = 0
    skipped = 0
    errors = 0
    
    try:
        for username_dir in os.listdir(media_root):
            username_path = os.path.join(media_root, username_dir)
            if not os.path.isdir(username_path):
                continue
            
            username = username_dir.lower()
            
            for filename in os.listdir(username_path):
                file_path = os.path.join(username_path, filename)
                if not os.path.isfile(file_path):
                    continue
                
                # Parse filename: {messageId}.{ext}
                match = re.match(r'^(\d+)\.(jpg|mp4|png|gif)$', filename)
                if not match:
                    skipped += 1
                    continue
                
                message_id = int(match.group(1))
                ext = match.group(2)
                kind = "photo" if ext in ("jpg", "png", "gif") else "video"
                
                # Check if already registered
                existing = await db.tg_media_assets.find_one({
                    "username": username,
                    "messageId": message_id,
                    "kind": kind
                })
                
                if existing:
                    skipped += 1
                    continue
                
                try:
                    size = os.path.getsize(file_path)
                    now = datetime.now(timezone.utc)
                    
                    await db.tg_media_assets.insert_one({
                        "username": username,
                        "messageId": message_id,
                        "kind": kind,
                        "localPath": file_path,
                        "url": f"/tg/media/{username}/{filename}",
                        "size": size,
                        "w": None,
                        "h": None,
                        "duration": None,
                        "mime": "image/jpeg" if kind == "photo" else "video/mp4",
                        "status": "READY",
                        "createdAt": now,
                        "lastAccessAt": now,
                        "pinned": False
                    })
                    registered += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"Failed to register {file_path}: {e}")
        
        return {
            "ok": True,
            "registered": registered,
            "skipped": skipped,
            "errors": errors
        }
    except Exception as e:
        logger.error(f"Media scan error: {e}")
        return {"ok": False, "error": str(e)}


# ============================================================================
# MEDIA BACKFILL WORKER (Production-safe controlled download)
# ============================================================================

MEDIA_BACKFILL_AVAILABLE = False
try:
    from telegram_lite.media_backfill_worker import (
        media_backfill_tick,
        get_backfill_status
    )
    MEDIA_BACKFILL_AVAILABLE = True
    logger.info("Media Backfill Worker loaded")
except ImportError as e:
    logger.warning(f"Media Backfill Worker not available: {e}")


@telegram_router.get("/admin/media/backfill/status")
async def get_media_backfill_status():
    """
    Get media backfill status and configuration.
    GET /api/telegram-intel/admin/media/backfill/status
    """
    if not MEDIA_BACKFILL_AVAILABLE:
        return {"ok": False, "error": "Media Backfill not available"}
    
    try:
        status = await get_backfill_status(db)
        return {"ok": True, **status}
    except Exception as e:
        logger.error(f"Backfill status error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/media/backfill/tick")
async def run_media_backfill_tick():
    """
    Run single media backfill tick.
    POST /api/telegram-intel/admin/media/backfill/tick
    
    SAFETY:
    - Only WATCHLIST channels
    - Only last 14 days
    - Only photos (no video)
    - Max 20 downloads per tick
    - 2.5s delay between downloads
    """
    if not MEDIA_BACKFILL_AVAILABLE or not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "Media Backfill or MTProto not available"}
    
    try:
        async with MTProtoConnection() as client:
            result = await media_backfill_tick(db, client, logger)
            return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Backfill tick error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Task 2: Scheduler v2 Routes ======================

@telegram_router.get("/admin/scheduler/status-v2")
async def get_scheduler_status_v2():
    """
    Get Scheduler v2 status (dual loop)
    GET /api/telegram-intel/admin/scheduler/status-v2
    """
    if not SCHEDULER_V2_AVAILABLE:
        return {"ok": False, "error": "Scheduler v2 not available"}
    
    try:
        state = await get_scheduler_state_v2(db)
        return state
    except Exception as e:
        logger.error(f"Scheduler v2 status error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/scheduler/tick-v2")
async def run_scheduler_tick_v2():
    """
    Run single Scheduler v2 tick (process both bands)
    POST /api/telegram-intel/admin/scheduler/tick-v2
    """
    if not SCHEDULER_V2_AVAILABLE or not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "Scheduler v2 or MTProto not available"}
    
    async def process_channel(db_ref, client, username):
        """Process single channel fetch"""
        try:
            messages = await client.get_channel_messages(username, limit=50, download_media=MEDIA_ENGINE_AVAILABLE, db=db_ref)
            if messages:
                now = datetime.now(timezone.utc)
                for msg in messages:
                    await db_ref.tg_posts.update_one(
                        {"username": username, "messageId": msg["messageId"]},
                        {"$set": {
                            "username": username,
                            "messageId": msg["messageId"],
                            "date": msg.get("date"),
                            "text": msg.get("text", "")[:1000],
                            "views": msg.get("views", 0),
                            "forwards": msg.get("forwards", 0),
                            "replies": msg.get("replies", 0),
                            "hasMedia": msg.get("hasMedia", False),
                            "mediaType": msg.get("mediaType"),
                            "mediaLocalPath": msg.get("mediaLocalPath"),
                            "mediaDownloaded": msg.get("mediaDownloaded", False),
                            "fetchedAt": now
                        }},
                        upsert=True
                    )
                return True
            return False
        except Exception as e:
            logger.error(f"Process channel {username} error: {e}")
            raise
    
    try:
        async with MTProtoConnection() as client:
            result = await scheduler_tick_v2(
                db, client, process_channel,
                max_base=10, max_watch=15
            )
            return result
    except Exception as e:
        logger.error(f"Scheduler v2 tick error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Task 3: Auth + Actor Routes ======================

@telegram_router.get("/auth/me")
async def auth_me(request: Request, response: Response):
    """
    Get current actor info (creates anonymous if new)
    GET /api/telegram-intel/auth/me
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        actor_info = await get_actor_info(db, actor["actorId"])
        
        return {
            "ok": True,
            "actor": {
                "actorId": actor["actorId"],
                "type": actor.get("type", "anonymous"),
                "isNew": actor.get("isNew", False),
                "createdAt": actor_info.get("createdAt").isoformat() if actor_info and actor_info.get("createdAt") else None
            }
        }
    except Exception as e:
        logger.error(f"Auth me error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/auth/reset")
async def auth_reset(response: Response):
    """
    Reset actor session (clear cookie)
    POST /api/telegram-intel/auth/reset
    """
    try:
        from telegram_lite.auth_actor import COOKIE_NAME
        response.delete_cookie(key=COOKIE_NAME, path="/")
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Actor-aware watchlist endpoints
@telegram_router.get("/watchlist/me")
async def get_my_watchlist(request: Request, response: Response):
    """
    Get current actor's watchlist
    GET /api/telegram-intel/watchlist/me
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        items = await get_actor_watchlist(db, actor["actorId"])
        return {"ok": True, "items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"Get watchlist error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/watchlist/me/add")
async def add_to_my_watchlist(request: Request, response: Response, body: dict = None):
    """
    Add channel to actor's watchlist
    POST /api/telegram-intel/watchlist/me/add
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        username = (body or {}).get("username", "")
        
        if not username:
            return {"ok": False, "error": "username required"}
        
        success = await actor_add_to_watchlist(db, actor["actorId"], username)
        return {"ok": success, "username": username.lower().replace("@", "")}
    except Exception as e:
        logger.error(f"Add to watchlist error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.delete("/watchlist/me/{username}")
async def remove_from_my_watchlist(username: str, request: Request, response: Response):
    """
    Remove channel from actor's watchlist
    DELETE /api/telegram-intel/watchlist/me/:username
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        success = await actor_remove_from_watchlist(db, actor["actorId"], username)
        return {"ok": success}
    except Exception as e:
        logger.error(f"Remove from watchlist error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/watchlist/me/check/{username}")
async def check_my_watchlist(username: str, request: Request, response: Response):
    """
    Check if channel is in actor's watchlist
    GET /api/telegram-intel/watchlist/me/check/:username
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        in_watchlist = await check_in_watchlist(db, actor["actorId"], username)
        return {"ok": True, "inWatchlist": in_watchlist}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Actor-aware feed state endpoints
@telegram_router.post("/feed/me/read")
async def mark_post_read(request: Request, response: Response, body: dict = None):
    """
    Mark post as read/unread for current actor
    POST /api/telegram-intel/feed/me/read
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        post_key = (body or {}).get("postKey", "")
        is_read = (body or {}).get("isRead", True)
        
        if not post_key:
            return {"ok": False, "error": "postKey required"}
        
        await set_post_read(db, actor["actorId"], post_key, is_read)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/feed/me/read/batch")
async def mark_posts_read_batch(request: Request, response: Response, body: dict = None):
    """
    Mark multiple posts as read/unread for current actor (batch)
    POST /api/telegram-intel/feed/me/read/batch
    {"postKeys": ["incrypted:123", "cryptodep:999"], "isRead": true}
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        post_keys = (body or {}).get("postKeys", [])
        is_read = (body or {}).get("isRead", True)
        
        if not post_keys or not isinstance(post_keys, list):
            return {"ok": False, "error": "postKeys array required"}
        
        # Limit batch size
        post_keys = post_keys[:100]
        
        updated = 0
        now = datetime.now(timezone.utc)
        
        for post_key in post_keys:
            if not post_key:
                continue
            await db.tg_feed_state.update_one(
                {"actorId": actor["actorId"], "postKey": post_key},
                {
                    "$set": {
                        "actorId": actor["actorId"],
                        "postKey": post_key,
                        "isRead": is_read,
                        "updatedAt": now
                    }
                },
                upsert=True
            )
            updated += 1
        
        return {"ok": True, "updated": updated}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/feed/me/pin")
async def toggle_post_pin(request: Request, response: Response, body: dict = None):
    """
    Pin/unpin post for current actor
    POST /api/telegram-intel/feed/me/pin
    
    Accepts either:
    - postKey: "username:messageId"
    - OR username + messageId separately
    """
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        body = body or {}
        
        # Support both postKey and username+messageId formats
        post_key = body.get("postKey", "")
        if not post_key:
            username = body.get("username", "")
            message_id = body.get("messageId", "")
            if username and message_id:
                post_key = f"{username}:{message_id}"
        
        is_pinned = body.get("isPinned", True)
        
        if not post_key:
            return {"ok": False, "error": "postKey or username+messageId required"}
        
        await set_post_pinned(db, actor["actorId"], post_key, is_pinned)
        logger.info(f"Pin toggled: actor={actor['actorId'][:20]}, post={post_key}, pinned={is_pinned}")
        return {"ok": True, "postKey": post_key, "isPinned": is_pinned}
    except Exception as e:
        logger.error(f"Pin error: {e}")
        return {"ok": False, "error": str(e)}


# ============================================================================
# INTELLIGENCE LAYER (A1, A2, A3) + CACHE (C) + ALERTS (D)
# ============================================================================

INTELLIGENCE_AVAILABLE = False
ALERTS_AVAILABLE = False
try:
    from telegram_lite.intelligence import (
        extract_topics,
        TopicRepository,
        TopicMomentumEngine,
        AnomalyRepository,
        AnomalyEngine,
        CrossChannelSignalService,
        ensure_topic_indexes,
        ensure_signal_indexes,
        FeedCacheRepository,
        TopicMomentumCacheRepository,
        AnomalyCacheRepository,
        ensure_cache_indexes,
        AlertRepository,
        AlertPreferencesRepository,
        AlertCore,
        ensure_alert_indexes
    )
    INTELLIGENCE_AVAILABLE = True
    ALERTS_AVAILABLE = True
    logger.info("Intelligence Layer + Alerts loaded")
except ImportError as e:
    logger.warning(f"Intelligence Layer not available: {e}")


@telegram_router.get("/topics/momentum")
async def get_topic_momentum(limit: int = 20):
    """
    A1: Topic Momentum Engine
    GET /api/telegram-intel/topics/momentum
    
    Returns trending topics with momentum scores.
    """
    try:
        # Try intelligence layer first
        if INTELLIGENCE_AVAILABLE:
            try:
                repo = TopicRepository(db)
                engine = TopicMomentumEngine(repo)
                topics = await engine.calculate(limit=limit)
                if topics:
                    return {
                        "ok": True,
                        "windowHours": 6,
                        "topics": topics
                    }
            except Exception as e:
                logger.warning(f"TopicMomentumEngine error: {e}")
        
        # Fallback to topic_mentions collection
        topics = await db.topic_mentions.find(
            {},
            {"_id": 0}
        ).sort("momentum", -1).limit(limit).to_list(limit)
        
        return {
            "ok": True,
            "windowHours": 6,
            "topics": topics
        }
    except Exception as e:
        logger.error(f"Topic momentum error: {e}")
        return {"ok": False, "error": str(e), "topics": []}


@telegram_router.get("/momentum/top")
async def get_momentum_top(limit: int = 20, days: int = 7):
    """
    Get top channels by momentum score.
    GET /api/telegram-intel/momentum/top
    """
    try:
        # Get channels with recent activity and compute momentum
        channels = await db.tg_channel_states.find(
            {"eligible": True},
            {"_id": 0}
        ).sort("participantsCount", -1).limit(limit * 2).to_list(limit * 2)
        
        result = []
        for ch in channels:
            username = ch.get("username", "")
            
            # Compute momentum from growth and activity
            growth7 = ch.get("growth7", 0) or 0
            growth30 = ch.get("growth30", 0) or 0
            members = ch.get("participantsCount", 0) or 1
            
            # Simple momentum calculation
            momentum = (growth7 * 2 + growth30) / 3 * 100
            velocity = growth7 - (growth30 / 4) if growth30 else growth7
            
            result.append({
                "username": username,
                "title": ch.get("title", username),
                "avatarUrl": ch.get("avatarUrl"),
                "members": members,
                "momentum": round(momentum, 2),
                "velocity": round(velocity * 100, 2),
                "growth7": round(growth7 * 100, 2),
                "growth30": round(growth30 * 100, 2),
                "trend": "up" if momentum > 0 else "down" if momentum < 0 else "stable"
            })
        
        # Sort by momentum
        result.sort(key=lambda x: abs(x["momentum"]), reverse=True)
        
        return {
            "ok": True,
            "items": result[:limit],
            "total": len(result),
            "days": days
        }
    except Exception as e:
        logger.error(f"Momentum top error: {e}")
        return {"ok": False, "error": str(e), "items": []}


@telegram_router.get("/momentum/movers")
async def get_momentum_movers(limit: int = 20, days: int = 7):
    """
    Get channels with biggest momentum changes.
    GET /api/telegram-intel/momentum/movers
    """
    try:
        channels = await db.tg_channel_states.find(
            {"eligible": True},
            {"_id": 0}
        ).sort("participantsCount", -1).limit(limit * 3).to_list(limit * 3)
        
        gainers = []
        losers = []
        
        for ch in channels:
            username = ch.get("username", "")
            growth7 = ch.get("growth7", 0) or 0
            growth30 = ch.get("growth30", 0) or 0
            
            change = growth7 * 100
            
            item = {
                "username": username,
                "title": ch.get("title", username),
                "avatarUrl": ch.get("avatarUrl"),
                "members": ch.get("participantsCount", 0),
                "change": round(change, 2),
                "growth7": round(growth7 * 100, 2)
            }
            
            if change > 0:
                gainers.append(item)
            elif change < 0:
                losers.append(item)
        
        gainers.sort(key=lambda x: x["change"], reverse=True)
        losers.sort(key=lambda x: x["change"])
        
        return {
            "ok": True,
            "gainers": gainers[:limit//2],
            "losers": losers[:limit//2],
            "days": days
        }
    except Exception as e:
        logger.error(f"Momentum movers error: {e}")
        return {"ok": False, "error": str(e), "gainers": [], "losers": []}


@telegram_router.get("/movers")
async def get_movers(limit: int = 20, days: int = 7, metric: str = "growth"):
    """
    Get top movers by score change.
    GET /api/telegram-intel/movers
    """
    try:
        channels = await db.tg_channel_states.find(
            {"eligible": True},
            {"_id": 0}
        ).sort("participantsCount", -1).limit(limit * 2).to_list(limit * 2)
        
        result = []
        for ch in channels:
            username = ch.get("username", "")
            growth7 = ch.get("growth7", 0) or 0
            
            result.append({
                "username": username,
                "title": ch.get("title", username),
                "avatarUrl": ch.get("avatarUrl"),
                "members": ch.get("participantsCount", 0),
                "change": round(growth7 * 100, 2),
                "metric": metric
            })
        
        result.sort(key=lambda x: abs(x["change"]), reverse=True)
        
        return {
            "ok": True,
            "items": result[:limit],
            "metric": metric,
            "days": days
        }
    except Exception as e:
        logger.error(f"Movers error: {e}")
        return {"ok": False, "error": str(e), "items": []}


@telegram_router.get("/temporal/top-movers")
async def get_temporal_top_movers(limit: int = 20, days: int = 7):
    """
    Get temporal top movers.
    GET /api/telegram-intel/temporal/top-movers
    """
    return await get_movers(limit=limit, days=days, metric="temporal")


@telegram_router.get("/signals")
async def get_signals_list(limit: int = 50, days: int = 7, type: str = None, severity: str = None):
    """
    Get signals list.
    GET /api/telegram-intel/signals
    """
    try:
        filter_q = {}
        if type:
            filter_q["type"] = type
        if severity:
            filter_q["severity"] = severity
        
        # Get from alert_logs as signals
        signals = await db.alert_logs.find(
            filter_q,
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        # Format for frontend
        result = []
        for s in signals:
            result.append({
                "id": str(s.get("_id", "")),
                "type": s.get("type", "UNKNOWN"),
                "severity": s.get("priority", 1),
                "channel": s.get("meta", {}).get("channel"),
                "topic": s.get("meta", {}).get("topic"),
                "message": s.get("meta", {}).get("summary", ""),
                "createdAt": s.get("createdAt").isoformat() if s.get("createdAt") else None
            })
        
        return {
            "ok": True,
            "items": result,
            "total": len(result)
        }
    except Exception as e:
        logger.error(f"Signals list error: {e}")
        return {"ok": False, "error": str(e), "items": []}


@telegram_router.get("/lifecycle/transitions")
async def get_lifecycle_transitions(limit: int = 50, days: int = 7):
    """
    Get lifecycle transitions.
    GET /api/telegram-intel/lifecycle/transitions
    """
    try:
        # Get channels with lifecycle info
        channels = await db.tg_channel_states.find(
            {"eligible": True},
            {"_id": 0, "username": 1, "title": 1, "lifecycle": 1, "growth7": 1}
        ).sort("participantsCount", -1).limit(limit).to_list(limit)
        
        result = []
        for ch in channels:
            lifecycle = ch.get("lifecycle") or classify_lifecycle(ch)
            result.append({
                "username": ch.get("username"),
                "title": ch.get("title"),
                "currentStage": lifecycle,
                "previousStage": None,
                "transitionDate": None
            })
        
        return {
            "ok": True,
            "items": result,
            "days": days
        }
    except Exception as e:
        logger.error(f"Lifecycle transitions error: {e}")
        return {"ok": False, "error": str(e), "items": []}


@telegram_router.get("/signals/cross-channel")
async def get_cross_channel_signals(window: int = 30, refresh: bool = False):
    """
    A3: Cross-Channel Signal Engine
    GET /api/telegram-intel/signals/cross-channel?window=30
    
    Returns cross-channel market events (same topic in 3+ channels).
    """
    try:
        # Try intelligence layer first
        if INTELLIGENCE_AVAILABLE:
            try:
                service = CrossChannelSignalService(db)
                events = await service.get_signals(window_minutes=window, force_refresh=refresh)
                if events:
                    return {
                        "ok": True,
                        "windowMinutes": window,
                        "eventCount": len(events),
                        "events": events
                    }
            except Exception as e:
                logger.warning(f"CrossChannelSignalService error: {e}")
        
        # Fallback to cross_channel_signals collection
        now = datetime.now(timezone.utc)
        events = await db.cross_channel_signals.find(
            {"expiresAt": {"$gt": now}},
            {"_id": 0}
        ).sort("mentions", -1).to_list(20)
        
        return {
            "ok": True,
            "windowMinutes": window,
            "eventCount": len(events),
            "events": events
        }
    except Exception as e:
        logger.error(f"Cross-channel signal error: {e}")
        return {"ok": False, "error": str(e), "events": []}


@telegram_router.get("/posts/{username}/{message_id}/anomaly")
async def get_post_anomaly(username: str, message_id: int):
    """
    A2: Post Anomaly Check
    GET /api/telegram-intel/posts/:username/:messageId/anomaly
    
    Returns anomaly score for specific post.
    """
    if not INTELLIGENCE_AVAILABLE:
        return {"ok": False, "error": "Intelligence layer not available"}
    
    try:
        post = await db.tg_posts.find_one(
            {"username": username.lower(), "messageId": message_id},
            {"_id": 0}
        )
        
        if not post:
            return {"ok": False, "error": "Post not found"}
        
        repo = AnomalyRepository(db)
        engine = AnomalyEngine(repo)
        result = await engine.evaluate_post(post)
        
        if not result:
            return {"ok": True, "message": "Not enough data for anomaly detection"}
        
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Anomaly check error: {e}")
        return {"ok": False, "error": str(e)}


# ============================================================================
# ALERT SYSTEM (D)
# ============================================================================

@telegram_router.get("/alerts")
async def get_alerts(actorId: str = DEFAULT_ACTOR_ID, hours: int = 24, limit: int = 50):
    """
    Get recent alerts for actor.
    GET /api/telegram-intel/alerts?actorId=xxx&hours=24
    """
    if not ALERTS_AVAILABLE:
        return {"ok": False, "error": "Alerts not available"}
    
    try:
        repo = AlertRepository(db)
        alerts = await repo.get_recent(actorId, hours=hours, limit=limit)
        
        return {
            "ok": True,
            "actorId": actorId,
            "count": len(alerts),
            "alerts": alerts
        }
    except Exception as e:
        logger.error(f"Get alerts error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/alerts/preferences")
async def get_alert_preferences(actorId: str = DEFAULT_ACTOR_ID):
    """
    Get alert preferences for actor.
    GET /api/telegram-intel/alerts/preferences?actorId=xxx
    """
    if not ALERTS_AVAILABLE:
        return {"ok": False, "error": "Alerts not available"}
    
    try:
        repo = AlertPreferencesRepository(db)
        prefs = await repo.get(actorId)
        
        if not prefs:
            prefs = await repo.get_defaults()
            prefs["actorId"] = actorId
        
        return {"ok": True, **prefs}
    except Exception as e:
        logger.error(f"Get preferences error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/alerts/preferences")
async def update_alert_preferences(request: Request):
    """
    Update alert preferences for actor.
    POST /api/telegram-intel/alerts/preferences
    
    Body: { actorId, enabled, allowedTypes, minSeverity, cooldownMinutes }
    """
    if not ALERTS_AVAILABLE:
        return {"ok": False, "error": "Alerts not available"}
    
    try:
        body = await request.json()
        actor_id = body.get("actorId", DEFAULT_ACTOR_ID)
        
        update_data = {}
        if "enabled" in body:
            update_data["enabled"] = bool(body["enabled"])
        if "allowedTypes" in body:
            update_data["allowedTypes"] = body["allowedTypes"]
        if "minSeverity" in body:
            update_data["minSeverity"] = body["minSeverity"]
        if "cooldownMinutes" in body:
            update_data["cooldownMinutes"] = int(body["cooldownMinutes"])
        
        repo = AlertPreferencesRepository(db)
        await repo.upsert(actor_id, update_data)
        
        return {"ok": True, "updated": update_data}
    except Exception as e:
        logger.error(f"Update preferences error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/alerts/process")
async def process_alerts_now(actorId: str = DEFAULT_ACTOR_ID):
    """
    Manually trigger alert processing for actor.
    POST /api/telegram-intel/alerts/process?actorId=xxx
    """
    if not ALERTS_AVAILABLE or not INTELLIGENCE_AVAILABLE:
        return {"ok": False, "error": "Intelligence/Alerts not available"}
    
    try:
        # Get current signals
        signal_service = CrossChannelSignalService(db)
        signals = await signal_service.get_signals(30)
        
        # Get topic momentum
        topic_repo = TopicRepository(db)
        topic_engine = TopicMomentumEngine(topic_repo)
        topics = await topic_engine.calculate(limit=10)
        
        # Process alerts
        alert_core = AlertCore(db)
        
        topic_count = await alert_core.process_topic_spikes(topics, actorId)
        signal_count = await alert_core.process_cross_signals(signals, actorId)
        
        return {
            "ok": True,
            "actorId": actorId,
            "alertsGenerated": {
                "topicSpikes": topic_count,
                "crossSignals": signal_count
            }
        }
    except Exception as e:
        logger.error(f"Process alerts error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Task 4: Delivery Bot Routes ======================

@telegram_router.post("/link/telegram/start")
async def start_telegram_link(request: Request, response: Response):
    """
    Generate link code for Telegram connection
    POST /api/telegram-intel/link/telegram/start
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    if not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Auth system not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        link_data = await create_link_code(db, actor["actorId"])
        return {"ok": True, **link_data}
    except Exception as e:
        logger.error(f"Create link code error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/link/telegram/status")
async def get_telegram_link_status(request: Request, response: Response):
    """
    Get current actor's Telegram link status
    GET /api/telegram-intel/link/telegram/status
    """
    if not DELIVERY_BOT_AVAILABLE or not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Required modules not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        status = await get_actor_link_status(db, actor["actorId"])
        return {"ok": True, **status}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@telegram_router.post("/link/telegram/revoke")
async def revoke_telegram_link(request: Request, response: Response):
    """
    Revoke Telegram link
    POST /api/telegram-intel/link/telegram/revoke
    """
    if not DELIVERY_BOT_AVAILABLE or not AUTH_ACTOR_AVAILABLE:
        return {"ok": False, "error": "Required modules not available"}
    
    try:
        actor = await get_or_create_actor(db, request, response)
        success = await revoke_actor_link(db, actor["actorId"])
        return {"ok": success}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# Bot webhook endpoint (Telegram calls this) - production with secret verification
@telegram_router.post("/bot/webhook/{token}")
async def telegram_bot_webhook(token: str, request: Request):
    """
    Telegram Bot webhook handler (legacy with token in URL)
    POST /api/telegram-intel/bot/webhook/:token
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False}
    
    # Validate token
    if token != BOT_TOKEN:
        return {"ok": False, "error": "Invalid token"}
    
    try:
        body = await request.json()
        result = await handle_bot_update(db, body)
        return result
    except Exception as e:
        logger.error(f"Bot webhook error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/bot/webhook")
async def telegram_bot_webhook_secure(request: Request):
    """
    Telegram Bot webhook handler (production with secret header)
    POST /api/telegram-intel/bot/webhook
    
    Handles both delivery_bot and geo_bot updates
    Requires X-Telegram-Bot-Api-Secret-Token header
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False}
    
    from telegram_lite.delivery_bot import verify_webhook_secret, WEBHOOK_SECRET
    
    # Verify secret token
    secret_header = request.headers.get("x-telegram-bot-api-secret-token", "")
    if WEBHOOK_SECRET and not verify_webhook_secret(secret_header):
        logger.warning("Invalid webhook secret token")
        raise HTTPException(status_code=403, detail="Invalid secret token")
    
    try:
        body = await request.json()
        
        # Process with Geo Radar Bot first (handles /start, /radar_on, /radar_off, /status, /test)
        try:
            from geo_intel.services.bot import get_bot
            geo_bot = get_bot(db)
            await geo_bot.process_update(body)
            logger.info("Update processed by Geo Radar Bot")
        except Exception as e:
            logger.warning(f"Geo bot processing error (non-critical): {e}")
        
        # Also process with delivery bot for linking/alerts
        result = await handle_bot_update(db, body)
        return result
    except Exception as e:
        logger.error(f"Bot webhook error: {e}")
        return {"ok": False, "error": str(e)}


# Webhook management endpoints
@telegram_router.post("/admin/bot/webhook/set")
async def set_bot_webhook(body: dict = None):
    """
    Set Telegram Bot webhook URL
    POST /api/telegram-intel/admin/bot/webhook/set
    {"url": "https://yourdomain.com/api/telegram-intel/bot/webhook"}
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    from telegram_lite.delivery_bot import set_webhook
    
    webhook_url = (body or {}).get("url", "")
    if not webhook_url:
        return {"ok": False, "error": "url required"}
    
    result = await set_webhook(webhook_url)
    return result


@telegram_router.get("/bot/status")
async def get_bot_status():
    """
    Get Telegram Bot status and configuration
    GET /api/telegram-intel/bot/status
    """
    from telegram_lite.delivery_bot import BOT_TOKEN, BOT_USERNAME, get_webhook_info
    
    bot_configured = bool(BOT_TOKEN)
    webhook_info = None
    bot_info = None
    
    if bot_configured:
        # Get webhook info
        webhook_result = await get_webhook_info()
        if webhook_result.get("ok"):
            webhook_info = webhook_result.get("result", {})
        
        # Get bot info
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe")
                bot_data = resp.json()
                if bot_data.get("ok"):
                    bot_info = bot_data.get("result", {})
        except Exception as e:
            logger.warning(f"Get bot info failed: {e}")
    
    # Get delivery stats
    pending_count = 0
    sent_count = 0
    failed_count = 0
    linked_users = 0
    
    try:
        pending_count = await db.tg_delivery_outbox.count_documents({"status": "PENDING"})
        sent_count = await db.tg_delivery_outbox.count_documents({"status": "SENT"})
        failed_count = await db.tg_delivery_outbox.count_documents({"status": "FAILED"})
        linked_users = await db.tg_actor_links.count_documents({"provider": "telegram", "revokedAt": None})
    except:
        pass
    
    webhook_active = bool(webhook_info and webhook_info.get("url"))
    
    return {
        "ok": True,
        "botConfigured": bot_configured,
        "botInfo": {
            "username": bot_info.get("username") if bot_info else BOT_USERNAME,
            "firstName": bot_info.get("first_name") if bot_info else None,
            "canJoinGroups": bot_info.get("can_join_groups") if bot_info else None,
            "canReadAllGroupMessages": bot_info.get("can_read_all_group_messages") if bot_info else None
        } if bot_configured else None,
        "webhook": {
            "active": webhook_active,
            "url": webhook_info.get("url") if webhook_info else None,
            "hasCustomCertificate": webhook_info.get("has_custom_certificate") if webhook_info else False,
            "pendingUpdateCount": webhook_info.get("pending_update_count") if webhook_info else 0,
            "lastErrorDate": webhook_info.get("last_error_date") if webhook_info else None,
            "lastErrorMessage": webhook_info.get("last_error_message") if webhook_info else None
        },
        "delivery": {
            "linkedUsers": linked_users,
            "pendingMessages": pending_count,
            "sentMessages": sent_count,
            "failedMessages": failed_count
        },
        "requirements": {
            "webhookNeeded": not webhook_active,
            "webhookUrl": f"https://{os.environ.get('HOSTNAME', 'yourdomain.com')}/api/telegram-intel/bot/webhook"
        }
    }


@telegram_router.get("/admin/bot/webhook/info")
async def get_bot_webhook_info():
    """
    Get current webhook info
    GET /api/telegram-intel/admin/bot/webhook/info
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    from telegram_lite.delivery_bot import get_webhook_info
    
    result = await get_webhook_info()
    return result


@telegram_router.delete("/admin/bot/webhook")
async def delete_bot_webhook():
    """
    Delete webhook (switch to polling mode)
    DELETE /api/telegram-intel/admin/bot/webhook
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    from telegram_lite.delivery_bot import delete_webhook
    
    result = await delete_webhook()
    return result


@telegram_router.post("/admin/delivery/pump")
async def run_delivery_pump():
    """
    Distribute alerts + run delivery worker
    POST /api/telegram-intel/admin/delivery/pump
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    try:
        # 1. Distribute alerts to outbox
        dist_result = await distribute_alerts_to_telegram(db)
        
        # 2. Send from outbox
        worker_result = await run_delivery_worker(db, max_batch=50)
        
        return {
            "ok": True,
            "queued": dist_result.get("queued", 0),
            "sent": worker_result.get("sent", 0),
            "failed": worker_result.get("failed", 0)
        }
    except Exception as e:
        logger.error(f"Delivery pump error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/delivery/worker")
async def run_delivery_worker_endpoint():
    """
    Run delivery worker only (send pending messages)
    POST /api/telegram-intel/admin/delivery/worker
    """
    if not DELIVERY_BOT_AVAILABLE:
        return {"ok": False, "error": "Delivery Bot not available"}
    
    try:
        result = await run_delivery_worker(db, max_batch=100)
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Delivery worker error: {e}")
        return {"ok": False, "error": str(e)}


# ====================== Guardrails & Ops Routes ======================

@telegram_router.get("/admin/guardrails")
async def get_guardrails():
    """
    Get system guardrails configuration
    GET /api/telegram-intel/admin/guardrails
    """
    return {
        "ok": True,
        "guardrails": {
            "media": {
                "maxSizeMB": int(os.environ.get('TG_MEDIA_MAX_MB', '20')),
                "gcDays": int(os.environ.get('TG_MEDIA_GC_DAYS', '30')),
                "diskSoftLimitMB": int(os.environ.get('TG_DISK_SOFT_LIMIT_MB', '5000')),
                "diskHardLimitMB": int(os.environ.get('TG_DISK_HARD_LIMIT_MB', '8000'))
            },
            "scheduler": {
                "baseUnitsPerHour": int(os.environ.get('SCHEDULER_BASE_UNITS_PER_HOUR', '400')),
                "watchlistUnitsPerHour": int(os.environ.get('SCHEDULER_WATCHLIST_UNITS_PER_HOUR', '200')),
                "fetchCost": int(os.environ.get('SCHEDULER_FETCH_COST', '12'))
            },
            "delivery": {
                "sendRps": int(os.environ.get('TG_SEND_RPS', '20')),
                "linkCodeTtlMin": int(os.environ.get('TG_LINK_CODE_TTL_MIN', '30'))
            }
        },
        "modules": {
            "mediaEngine": MEDIA_ENGINE_AVAILABLE,
            "schedulerV2": SCHEDULER_V2_AVAILABLE,
            "authActor": AUTH_ACTOR_AVAILABLE,
            "deliveryBot": DELIVERY_BOT_AVAILABLE,
            "mtproto": MTPROTO_AVAILABLE
        }
    }


@telegram_router.get("/admin/ops/health")
async def ops_health_check():
    """
    System health check for all modules
    GET /api/telegram-intel/admin/ops/health
    """
    health = {
        "ok": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {}
    }
    
    # MongoDB check
    try:
        await db.command("ping")
        health["checks"]["mongodb"] = {"status": "ok"}
    except Exception as e:
        health["checks"]["mongodb"] = {"status": "error", "error": str(e)}
        health["ok"] = False
    
    # MTProto check
    if MTPROTO_AVAILABLE:
        try:
            async with MTProtoConnection() as client:
                connected = await client.connect()
                health["checks"]["mtproto"] = {"status": "ok" if connected else "disconnected"}
        except Exception as e:
            health["checks"]["mtproto"] = {"status": "error", "error": str(e)}
    else:
        health["checks"]["mtproto"] = {"status": "not_loaded"}
    
    # Media storage check
    if MEDIA_ENGINE_AVAILABLE:
        try:
            stats = await get_media_stats(db)
            disk_pct = (stats["diskUsageMB"] / stats["diskLimitMB"]) * 100
            health["checks"]["mediaStorage"] = {
                "status": "ok" if disk_pct < 80 else "warning",
                "usagePct": round(disk_pct, 1)
            }
        except Exception as e:
            health["checks"]["mediaStorage"] = {"status": "error", "error": str(e)}
    
    # Delivery Bot check
    if DELIVERY_BOT_AVAILABLE:
        pending = await db.tg_delivery_outbox.count_documents({"status": "PENDING"})
        failed = await db.tg_delivery_outbox.count_documents({"status": "FAILED"})
        health["checks"]["deliveryBot"] = {
            "status": "ok",
            "pendingMessages": pending,
            "failedMessages": failed
        }
    
    return health




@telegram_router.get("/admin/scheduler/status")
async def get_scheduler_status():
    """
    Get scheduler status
    GET /api/telegram-intel/admin/scheduler/status
    """
    if not SCHEDULER_LOADED:
        return {"ok": False, "error": "Scheduler module not loaded"}
    
    try:
        state = await get_scheduler_state(db)
        # Remove _id for JSON serialization
        if state and "_id" in state:
            state = {k: v for k, v in state.items() if k != "_id"}
        return {"ok": True, "state": state}
    except Exception as e:
        logger.error(f"Scheduler status error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/scheduler/enable")
async def enable_scheduler():
    """
    Enable and start scheduler
    POST /api/telegram-intel/admin/scheduler/enable
    """
    if not SCHEDULER_LOADED or not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "Scheduler or MTProto not available"}
    
    try:
        async with MTProtoConnection() as client:
            await start_scheduler(
                db, 
                client, 
                write_members_history,
                build_channel_snapshot
            )
        return {"ok": True, "status": "enabled"}
    except Exception as e:
        logger.error(f"Scheduler enable error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/scheduler/disable")
async def disable_scheduler():
    """
    Disable and stop scheduler
    POST /api/telegram-intel/admin/scheduler/disable
    """
    if not SCHEDULER_LOADED:
        return {"ok": False, "error": "Scheduler module not loaded"}
    
    try:
        await stop_scheduler(db)
        return {"ok": True, "status": "disabled"}
    except Exception as e:
        logger.error(f"Scheduler disable error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.post("/admin/scheduler/tick")
async def manual_scheduler_tick():
    """
    Run single scheduler tick manually
    POST /api/telegram-intel/admin/scheduler/tick
    """
    if not SCHEDULER_LOADED or not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "Scheduler or MTProto not available"}
    
    try:
        # Enable temporarily for this tick
        await set_scheduler_state(db, {"enabled": True})
        
        async with MTProtoConnection() as client:
            result = await scheduler_tick(
                db, 
                client, 
                write_members_history,
                build_channel_snapshot
            )
        
        return {"ok": True, "result": result}
    except Exception as e:
        logger.error(f"Scheduler tick error: {e}")
        return {"ok": False, "error": str(e)}


@telegram_router.get("/admin/scheduler/queue")
async def get_scheduler_queue():
    """
    Get next channels in scheduler queue
    GET /api/telegram-intel/admin/scheduler/queue
    """
    if not SCHEDULER_LOADED:
        return {"ok": False, "error": "Scheduler module not loaded"}
    
    try:
        batch = await pick_batch(db)
        return {
            "ok": True,
            "queueSize": len(batch),
            "channels": [
                {
                    "username": ch.get("username"),
                    "title": ch.get("title"),
                    "members": ch.get("participantsCount"),
                    "utilityScore": ch.get("utilityScore"),
                    "nextDueAt": ch.get("nextDueAt"),
                    "lastFetchedAt": ch.get("lastFetchedAt"),
                }
                for ch in batch
            ]
        }
    except Exception as e:
        logger.error(f"Scheduler queue error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Eligibility & Queue Routes (P0 Taск) ======================

@telegram_router.get("/admin/eligibility/stats")
async def get_eligibility_stats():
    """
    Get eligibility statistics
    GET /api/telegram-intel/admin/eligibility/stats
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Eligibility module not loaded"}
    
    try:
        stats = await get_queue_stats(db)
        return stats
    except Exception as e:
        logger.error(f"Eligibility stats error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/eligibility/evaluate")
async def evaluate_eligibility_batch(limit: int = 100):
    """
    Batch evaluate eligibility for channels
    POST /api/telegram-intel/admin/eligibility/evaluate
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Eligibility module not loaded"}
    
    try:
        result = await batch_evaluate_eligibility(db, limit)
        return result
    except Exception as e:
        logger.error(f"Eligibility evaluate error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/eligibility/channel/{username}")
async def get_channel_eligibility(username: str):
    """
    Get eligibility status for a specific channel
    GET /api/telegram-intel/admin/eligibility/channel/:username
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Eligibility module not loaded"}
    
    try:
        clean_username = normalize_username(username)
        channel = await db.tg_channel_states.find_one({"username": clean_username})
        
        if not channel:
            return {"ok": False, "error": "Channel not found"}
        
        eligibility = channel.get("eligibility", {})
        
        return {
            "ok": True,
            "username": clean_username,
            "eligibility": {
                "status": eligibility.get("status", "UNKNOWN"),
                "reasons": eligibility.get("reasons", []),
                "details": eligibility.get("details", {}),
                "evaluatedAt": eligibility.get("evaluatedAt").isoformat() if eligibility.get("evaluatedAt") else None,
            },
            "participantsCount": channel.get("participantsCount"),
            "lastPostAt": channel.get("lastPostAt").isoformat() if channel.get("lastPostAt") else None,
            "nextRunAt": channel.get("nextRunAt").isoformat() if channel.get("nextRunAt") else None,
        }
    except Exception as e:
        logger.error(f"Channel eligibility error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/eligibility/channel/{username}/evaluate")
async def evaluate_single_channel(username: str):
    """
    Evaluate eligibility for a single channel
    POST /api/telegram-intel/admin/eligibility/channel/:username/evaluate
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Eligibility module not loaded"}
    
    try:
        result = await evaluate_and_save_eligibility(db, normalize_username(username))
        return result
    except Exception as e:
        logger.error(f"Single channel eligibility error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/queue/candidates")
async def get_queue_candidates_api(limit: int = 30):
    """
    Get channels ready for ingestion
    GET /api/telegram-intel/admin/queue/candidates
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Queue module not loaded"}
    
    try:
        candidates = await get_queue_candidates(db, limit)
        return {
            "ok": True,
            "count": len(candidates),
            "candidates": [
                {
                    "username": c.get("username"),
                    "priority": c.get("priority"),
                    "eligibility": c.get("eligibility", {}).get("status"),
                    "participantsCount": c.get("participantsCount"),
                    "nextRunAt": c.get("nextRunAt").isoformat() if c.get("nextRunAt") else None,
                    "lastRefreshAt": c.get("lastRefreshAt").isoformat() if c.get("lastRefreshAt") else None,
                }
                for c in candidates
            ]
        }
    except Exception as e:
        logger.error(f"Queue candidates error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/queue/process")
async def process_queue_batch(limit: int = 10):
    """
    Process a batch of channels from the queue using MTProto
    POST /api/telegram-intel/admin/queue/process
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Queue module not loaded"}
    
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        # Get candidates
        candidates = await get_queue_candidates(db, limit)
        
        if not candidates:
            return {"ok": True, "message": "No candidates ready", "processed": 0}
        
        results = []
        
        async with MTProtoConnection() as client:
            for candidate in candidates:
                username = candidate.get("username")
                if not username:
                    continue
                
                # Fetch channel info
                info = await client.get_channel_info(username)
                
                if info and 'error' not in info:
                    # Get recent messages to determine lastPostAt
                    messages = await client.get_channel_messages(username, limit=10)
                    
                    last_post_at = None
                    if messages:
                        # Find most recent post date
                        for msg in messages:
                            if msg.get('date'):
                                try:
                                    post_date = datetime.fromisoformat(msg['date'].replace('Z', '+00:00'))
                                    if last_post_at is None or post_date > last_post_at:
                                        last_post_at = post_date
                                except:
                                    pass
                    
                    # Process result
                    process_result = await process_ingestion_result(
                        db,
                        username,
                        {
                            'ok': True,
                            'participantsCount': info.get('participantsCount'),
                            'lastPostAt': last_post_at,
                            'title': info.get('title'),
                        }
                    )
                    
                    results.append({
                        "username": username,
                        "ok": True,
                        "eligibility": process_result.get("eligibility"),
                        "participantsCount": info.get('participantsCount'),
                    })
                else:
                    # Handle error
                    error_type = info.get('error', 'UNKNOWN') if info else 'UNKNOWN'
                    process_result = await process_ingestion_result(
                        db,
                        username,
                        {'ok': False, 'error': error_type}
                    )
                    
                    results.append({
                        "username": username,
                        "ok": False,
                        "error": error_type,
                    })
        
        return {
            "ok": True,
            "processed": len(results),
            "results": results,
        }
    except Exception as e:
        logger.error(f"Queue process error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/channel/{username}/schedule")
async def schedule_channel_refresh(username: str):
    """
    Schedule next refresh for a channel based on its size
    POST /api/telegram-intel/admin/channel/:username/schedule
    """
    if not ELIGIBILITY_LOADED:
        return {"ok": False, "error": "Eligibility module not loaded"}
    
    try:
        result = await schedule_next_refresh(db, normalize_username(username))
        return result
    except Exception as e:
        logger.error(f"Schedule refresh error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Enhanced List with Eligibility Filter ======================

@telegram_router.get("/utility/list/eligible")
async def get_eligible_channels(
    q: Optional[str] = None,
    minMembers: Optional[int] = None,
    maxMembers: Optional[int] = None,
    minGrowth7: Optional[float] = None,
    maxGrowth7: Optional[float] = None,
    sort: str = "score",
    page: int = 1,
    limit: int = 25
):
    """
    Get list of ELIGIBLE Telegram channels only (excludes EXCLUDED)
    GET /api/telegram-intel/utility/list/eligible
    """
    try:
        # Build filter - only ELIGIBLE channels
        flt = {
            "$or": [
                {"eligibility.status": "ELIGIBLE"},
                {"eligibility": {"$exists": False}},  # Legacy channels without eligibility
            ]
        }
        
        if q:
            flt["$and"] = flt.get("$and", [])
            flt["$and"].append({
                "$or": [
                    {"username": {"$regex": q, "$options": "i"}},
                    {"title": {"$regex": q, "$options": "i"}},
                ]
            })
        
        if minMembers:
            flt["participantsCount"] = {"$gte": minMembers}
        if maxMembers:
            flt["participantsCount"] = {**flt.get("participantsCount", {}), "$lte": maxMembers}
        
        # Get channels from tg_channel_states
        cursor = db.tg_channel_states.find(flt).skip((page - 1) * limit).limit(limit)
        
        # Sort
        if sort == "members":
            cursor = cursor.sort("participantsCount", -1)
        elif sort == "growth":
            cursor = cursor.sort("growth7", -1)
        else:
            cursor = cursor.sort("priority", 1)
        
        channels = await cursor.to_list(limit)
        total = await db.tg_channel_states.count_documents(flt)
        
        # Get snapshots for additional metrics
        usernames = [c.get("username") for c in channels if c.get("username")]
        snapshots = {}
        if usernames:
            snap_cursor = db.tg_score_snapshots.find({"username": {"$in": usernames}}).sort("date", -1)
            for snap in await snap_cursor.to_list(len(usernames)):
                if snap["username"] not in snapshots:
                    snapshots[snap["username"]] = snap
        
        items = []
        for ch in channels:
            username = ch.get("username", "")
            snap = snapshots.get(username, {})
            
            members = ch.get("participantsCount") or ch.get("proxyMembers") or 0
            growth7 = snap.get("growth7", 0)
            
            # Generate sparkline
            random.seed(hash(username))
            sparkline = generate_sparkline_data(snap.get("utility", 50), growth7, 7)
            
            items.append({
                "username": username,
                "title": ch.get("title") or format_title(username),
                "avatarColor": generate_avatar_color(username),
                "type": "Group" if ch.get("isChannel") is False else "Channel",
                "members": members,
                "avgReach": int(members * snap.get("engagement", 0.1)),
                "growth7": growth7,
                "growth30": snap.get("growth30", 0),
                "activity": compute_activity_label(snap.get("postsPerDay", 2)),
                "fomoScore": snap.get("utility", 50),
                "utilityScore": snap.get("utility", 50),
                "fraudRisk": snap.get("fraud", 0.2),
                "stability": snap.get("stability", 0.7),
                "sparkline": sparkline,
                "eligibility": ch.get("eligibility", {}).get("status", "UNKNOWN"),
                "nextRunAt": ch.get("nextRunAt").isoformat() if ch.get("nextRunAt") else None,
            })
        
        return {
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": math.ceil(total / limit) if total > 0 else 1,
            "filter": "ELIGIBLE_ONLY",
        }
    except Exception as e:
        logger.error(f"Eligible list error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Budget Controller Routes ======================

@telegram_router.get("/admin/budget/status")
async def get_budget_status_api():
    """
    Get current MTProto budget status
    GET /api/telegram-intel/admin/budget/status
    """
    if not BUDGET_LOADED:
        return {"ok": False, "error": "Budget module not loaded"}
    
    try:
        status = await get_budget_status(db)
        cooldown = await is_cooldown_active(db)
        
        return {
            "ok": True,
            "budgets": status,
            "cooldown": cooldown,
        }
    except Exception as e:
        logger.error(f"Budget status error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/budget/init")
async def init_budget_api():
    """
    Initialize budget counters
    POST /api/telegram-intel/admin/budget/init
    """
    if not BUDGET_LOADED:
        return {"ok": False, "error": "Budget module not loaded"}
    
    try:
        await init_budgets(db)
        status = await get_budget_status(db)
        return {"ok": True, "budgets": status}
    except Exception as e:
        logger.error(f"Budget init error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Snapshot Validator Routes ======================

@telegram_router.post("/admin/snapshots/validate")
async def validate_snapshots_api(days: int = 30):
    """
    Validate snapshots and find anomalies
    POST /api/telegram-intel/admin/snapshots/validate
    """
    if not VALIDATOR_LOADED:
        return {"ok": False, "error": "Validator module not loaded"}
    
    try:
        result = await validate_snapshots(db, min(180, max(7, days)))
        return result
    except Exception as e:
        logger.error(f"Snapshot validate error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/anomalies/summary")
async def get_anomalies_api():
    """
    Get anomalies summary
    GET /api/telegram-intel/admin/anomalies/summary
    """
    if not VALIDATOR_LOADED:
        return {"ok": False, "error": "Validator module not loaded"}
    
    try:
        return await get_anomaly_summary(db)
    except Exception as e:
        logger.error(f"Anomalies summary error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/channel/{username}/check-growth")
async def check_artificial_growth_api(username: str):
    """
    Check channel for artificial growth
    POST /api/telegram-intel/admin/channel/:username/check-growth
    """
    if not VALIDATOR_LOADED:
        return {"ok": False, "error": "Validator module not loaded"}
    
    try:
        return await detect_artificial_growth(db, normalize_username(username))
    except Exception as e:
        logger.error(f"Growth check error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Discovery Engine Routes ======================

@telegram_router.post("/admin/discovery/expand")
async def discovery_expand(limit: int = 5):
    """
    Expand discovery from ELIGIBLE channels - extract candidates from posts.
    POST /api/telegram-intel/admin/discovery/expand
    """
    if not DISCOVERY_LOADED:
        return {"ok": False, "error": "Discovery module not loaded"}
    
    try:
        # Get ELIGIBLE channels
        channels = await db.tg_channel_states.find(
            {"eligibility.status": "ELIGIBLE"}
        ).limit(min(10, max(1, limit))).to_list(limit)
        
        total_discovered = 0
        total_saved = 0
        
        for ch in channels:
            username = ch.get("username")
            if not username:
                continue
            
            # Get utility score for priority calculation
            snap = await db.tg_score_snapshots.find_one(
                {"username": username},
                sort=[("date", -1)]
            )
            source_utility = snap.get("utility", 50) if snap else 50
            
            # Get posts
            posts = await db.tg_posts.find(
                {"username": username}
            ).sort("date", -1).limit(20).to_list(20)
            
            if not posts:
                continue
            
            # Extract candidates
            result = await extract_candidates_from_posts(db, username, posts, source_utility)
            candidates = result.get("candidates", [])
            
            if candidates:
                save_result = await save_candidates_to_queue(db, candidates)
                total_discovered += len(candidates)
                total_saved += save_result.get("saved", 0)
        
        return {
            "ok": True,
            "scanned": len(channels),
            "discovered": total_discovered,
            "saved": total_saved,
        }
    except Exception as e:
        logger.error(f"Discovery expand error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/discovery/promote")
async def discovery_promote(limit: int = 20):
    """
    Promote top candidates to ingestion queue.
    POST /api/telegram-intel/admin/discovery/promote
    """
    if not DISCOVERY_LOADED:
        return {"ok": False, "error": "Discovery module not loaded"}
    
    try:
        result = await promote_candidates_to_ingestion(db, min(20, max(1, limit)))
        return result
    except Exception as e:
        logger.error(f"Discovery promote error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/discovery/recalculate-priority")
async def discovery_recalculate():
    """
    Recalculate priorities for all NEW candidates.
    POST /api/telegram-intel/admin/discovery/recalculate-priority
    """
    if not DISCOVERY_LOADED:
        return {"ok": False, "error": "Discovery module not loaded"}
    
    try:
        result = await recalculate_candidate_priorities(db)
        return result
    except Exception as e:
        logger.error(f"Discovery recalculate error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/discovery/stats")
async def discovery_stats():
    """
    Get candidate queue statistics.
    GET /api/telegram-intel/admin/discovery/stats
    """
    if not DISCOVERY_LOADED:
        return {"ok": False, "error": "Discovery module not loaded"}
    
    try:
        return await get_candidate_stats(db)
    except Exception as e:
        logger.error(f"Discovery stats error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Network Influence Routes ======================

@telegram_router.post("/admin/network/build")
async def network_build(days: int = 30):
    """
    Build daily network scores.
    POST /api/telegram-intel/admin/network/build
    """
    if not NETWORK_LOADED:
        return {"ok": False, "error": "Network module not loaded"}
    
    try:
        result = await build_network_scores_daily(db, min(90, max(7, days)))
        return result
    except Exception as e:
        logger.error(f"Network build error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/network/list")
async def network_list(limit: int = 50):
    """
    Get network leaderboard (top by networkScore).
    GET /api/telegram-intel/network/list
    """
    if not NETWORK_LOADED:
        return {"ok": False, "error": "Network module not loaded"}
    
    try:
        return await get_network_leaderboard(db, min(200, max(1, limit)))
    except Exception as e:
        logger.error(f"Network list error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/channel/{username}/network/edges")
async def channel_network_edges(username: str, days: int = 30):
    """
    Get inbound/outbound network edges for a channel.
    GET /api/telegram-intel/channel/:username/network/edges
    """
    if not NETWORK_LOADED:
        return {"ok": False, "error": "Network module not loaded"}
    
    try:
        return await get_channel_network_edges(db, normalize_username(username), min(90, max(7, days)))
    except Exception as e:
        logger.error(f"Channel network edges error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/admin/network/stats")
async def network_stats():
    """
    Get network statistics.
    GET /api/telegram-intel/admin/network/stats
    """
    if not NETWORK_LOADED:
        return {"ok": False, "error": "Network module not loaded"}
    
    try:
        return await get_network_stats(db)
    except Exception as e:
        logger.error(f"Network stats error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Ingestion Tick (main scheduler endpoint) ======================

@telegram_router.post("/admin/ingestion/tick")
async def ingestion_tick(limit: int = 10):
    """
    Run one tick of ingestion scheduler with budget control.
    This is the main entry point for controlled ingestion.
    POST /api/telegram-intel/admin/ingestion/tick
    """
    if not ELIGIBILITY_LOADED or not BUDGET_LOADED:
        return {"ok": False, "error": "Required modules not loaded"}
    
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        # 1. Check cooldown
        cooldown = await is_cooldown_active(db)
        if cooldown.get("active"):
            return {
                "ok": False,
                "reason": "COOLDOWN_ACTIVE",
                "cooldown": cooldown,
            }
        
        # 2. Check budget
        budget_check = await budget_consume(db, cost=0)  # Just check, don't consume yet
        if not budget_check.get("ok"):
            return {
                "ok": False,
                "reason": budget_check.get("reason"),
                "budget": budget_check,
            }
        
        # 3. Get candidates
        candidates = await get_queue_candidates(db, min(30, max(1, limit)))
        
        if not candidates:
            return {"ok": True, "message": "No candidates ready", "processed": 0}
        
        results = []
        now = datetime.now(timezone.utc)
        
        async with MTProtoConnection() as client:
            for candidate in candidates:
                username = candidate.get("username")
                if not username:
                    continue
                
                # Check budget before each call (cost=3 for profile+messages)
                b = await budget_consume(db, cost=3)
                if not b.get("ok"):
                    results.append({
                        "username": username,
                        "ok": False,
                        "skipped": True,
                        "reason": "BUDGET_EXCEEDED",
                    })
                    break
                
                # Mark as running
                await db.tg_channel_states.update_one(
                    {"username": username},
                    {"$set": {"ingestionStatus": "RUNNING", "lastIngestionStartAt": now}}
                )
                
                try:
                    # Fetch channel info
                    info = await client.get_channel_info(username)
                    
                    if info and info.get('error') == 'FLOOD_WAIT':
                        # Record flood and stop
                        seconds = info.get('seconds', 60)
                        await record_flood_wait(db, seconds, username, "get_channel_info")
                        results.append({
                            "username": username,
                            "ok": False,
                            "error": "FLOOD_WAIT",
                            "seconds": seconds,
                        })
                        break
                    
                    if info and 'error' not in info:
                        # Get messages
                        messages = await client.get_channel_messages(username, limit=50)
                        
                        last_post_at = None
                        if messages:
                            for msg in messages:
                                if msg.get('date'):
                                    try:
                                        post_date = datetime.fromisoformat(msg['date'].replace('Z', '+00:00'))
                                        if last_post_at is None or post_date > last_post_at:
                                            last_post_at = post_date
                                    except:
                                        pass
                            
                            # Save posts
                            for msg in messages:
                                await db.tg_posts.update_one(
                                    {"username": username, "messageId": msg['messageId']},
                                    {"$set": {
                                        "username": username,
                                        "messageId": msg['messageId'],
                                        "date": msg['date'],
                                        "text": (msg.get('text') or '')[:1000],
                                        "views": msg.get('views', 0),
                                        "forwards": msg.get('forwards', 0),
                                        "hasMedia": msg.get('hasMedia', False),
                                        "fetchedAt": now,
                                    }},
                                    upsert=True
                                )
                        
                        # Process eligibility & schedule
                        process_result = await process_ingestion_result(
                            db, username,
                            {
                                'ok': True,
                                'participantsCount': info.get('participantsCount'),
                                'lastPostAt': last_post_at,
                                'title': info.get('title'),
                                'isPrivate': info.get('error') == 'PRIVATE',
                            }
                        )
                        
                        # Extract network edges from posts
                        if NETWORK_LOADED and messages:
                            try:
                                await upsert_edges_from_posts(db, username, messages)
                            except Exception as ne:
                                logger.warning(f"Network edges error for {username}: {ne}")
                        
                        # Update channel state
                        await db.tg_channel_states.update_one(
                            {"username": username},
                            {"$set": {
                                "title": info.get('title'),
                                "participantsCount": info.get('participantsCount'),
                                "isChannel": info.get('isChannel'),
                                "lastIngestionAt": now,
                                "lastIngestionOk": True,
                                "ingestionStatus": "DONE",
                                "lastPostAt": last_post_at,
                            }}
                        )
                        
                        results.append({
                            "username": username,
                            "ok": True,
                            "eligibility": process_result.get("eligibility"),
                            "participantsCount": info.get('participantsCount'),
                            "postsFound": len(messages) if messages else 0,
                        })
                    else:
                        # Error
                        error_type = info.get('error', 'UNKNOWN') if info else 'UNKNOWN'
                        
                        await process_ingestion_result(
                            db, username,
                            {'ok': False, 'error': error_type}
                        )
                        
                        await db.tg_channel_states.update_one(
                            {"username": username},
                            {"$set": {
                                "lastIngestionAt": now,
                                "lastIngestionOk": False,
                                "ingestionStatus": "ERROR",
                                "lastError": {"type": error_type, "at": now},
                            }}
                        )
                        
                        results.append({
                            "username": username,
                            "ok": False,
                            "error": error_type,
                        })
                        
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"Ingestion error for {username}: {error_msg}")
                    
                    await db.tg_channel_states.update_one(
                        {"username": username},
                        {"$set": {
                            "lastIngestionAt": now,
                            "lastIngestionOk": False,
                            "ingestionStatus": "ERROR",
                            "lastError": {"type": "EXCEPTION", "message": error_msg[:200], "at": now},
                        }}
                    )
                    
                    results.append({
                        "username": username,
                        "ok": False,
                        "error": error_msg[:100],
                    })
        
        # Get updated stats
        budget_status = await get_budget_status(db)
        eligibility_stats = await get_queue_stats(db)
        
        return {
            "ok": True,
            "processed": len(results),
            "results": results,
            "budget": budget_status,
            "eligibility": eligibility_stats.get("eligibility", {}),
        }
        
    except Exception as e:
        logger.error(f"Ingestion tick error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== P1: Seeds + Discovery + RU/UA Crypto Gate ======================

# Default RU/UA crypto seed list (20 channels)
DEFAULT_RU_CRYPTO_SEEDS = [
    "incrypted",
    "incrypted_headlines",
    "incrypted_airdrops",
    "doubletop",
    "idoresearch",
    "cryptomannnisnotacult",
    "toptradingview",
    "justhodling",
    "bulka_crypto",
    "moni_talks",
    "officer_cia",
    "lookonchain",
    "cryptoquant_official",
    "cryptodiffer",
    "cryptodep",
    "defillama_tg",
    "icodrops",
    "zachxbt",
    "peckshield",
    "paradigm_research",
]

# Enhanced crypto keywords for relevance scoring
CRYPTO_KEYWORDS_ENHANCED = [
    # General crypto
    "крипто", "крипта", "crypto", "blockchain", "блокчейн", "web3", "defi", "dex", "cex",
    "биткоин", "bitcoin", "btc", "eth", "ethereum", "эфир", "solana", "ton", "binance", "bsc",
    "airdrop", "airdrops", "дроп", "дропы", "ретродроп", "ретродропы", "фарм", "farm", "points", "поинты",
    "staking", "стейкинг", "restake", "рестейк", "l2", "zk", "zksync", "arbitrum", "optimism",
    "ido", "ico", "ieo", "whitelist", "вайтлист", "листинг", "listing", "launchpad", "лаунчпад",
    "onchain", "ончейн", "wallet", "кошелек", "gas", "газ", "bridge", "мост",
    # Trading
    "трейд", "трейдинг", "trade", "signals", "сигналы", "лонг", "шорт", "short", "long",
    "фьючерсы", "futures", "перп", "perps", "funding", "ликвидац", "liquidation",
    # Tokens
    "token", "токен", "tokenomics", "токеномика", "memecoin", "мемкоин", "nft",
]

# Negative keywords (non-crypto)
NON_CRYPTO_NEGATIVE = [
    "forex", "форекс", "ставки", "букмекер", "казино", "психология", "таро", "астролог",
    "недвижимость", "работа", "вакансия", "похуд", "фитнес", "рецепт",
]

def score_crypto_relevance_p1(text: str) -> dict:
    """Score crypto relevance with enhanced logic"""
    if not text:
        return {"score": 0, "hits": 0, "negative": 0}
    
    lower = text.lower()
    hits = sum(1 for kw in CRYPTO_KEYWORDS_ENHANCED if kw in lower)
    negative = sum(1 for neg in NON_CRYPTO_NEGATIVE if neg in lower)
    
    score = max(0, hits - negative * 3)
    return {"score": score, "hits": hits, "negative": negative}

def score_language_ru_ua_p1(text: str) -> dict:
    """Score RU/UA language confidence"""
    if not text:
        return {"lang": "UNKNOWN", "score": 0, "cyrillicRatio": 0}
    
    import re
    
    # UA specific chars
    ua_chars = len(re.findall(r'[їЇєЄіІґҐ]', text))
    # RU specific chars
    ru_chars = len(re.findall(r'[ёЁыЫэЭъЪ]', text))
    # General cyrillic
    cyrillic = len(re.findall(r'[а-яА-ЯіІїЇєЄёЁ]', text))
    total = max(1, len(text))
    
    cyrillic_ratio = cyrillic / total
    
    if cyrillic_ratio < 0.15:
        return {"lang": "OTHER", "score": 0, "cyrillicRatio": round(cyrillic_ratio, 2)}
    
    if ua_chars > ru_chars + 2:
        lang = "UA"
    else:
        lang = "RU"
    
    score = min(10, int(cyrillic_ratio * 15))
    return {"lang": lang, "score": score, "cyrillicRatio": round(cyrillic_ratio, 2)}

@telegram_router.post("/admin/seeds/import/default")
async def admin_import_default_seeds():
    """
    Import default RU/UA crypto seed channels
    POST /api/telegram-intel/admin/seeds/import/default
    """
    now = datetime.now(timezone.utc)
    inserted = 0
    skipped = 0
    
    for username in DEFAULT_RU_CRYPTO_SEEDS:
        clean_u = username.lower().strip()
        if not clean_u:
            continue
        
        # Check if exists
        exists = await db.tg_channel_states.find_one({"username": clean_u})
        if exists:
            skipped += 1
            continue
        
        # Insert as seed candidate
        await db.tg_channel_states.update_one(
            {"username": clean_u},
            {
                "$setOnInsert": {
                    "username": clean_u,
                    "stage": "CANDIDATE",
                    "source": "SEED_DEFAULT",
                    "priority": 10,  # High priority for seeds
                    "nextAllowedAt": now,
                    "createdAt": now,
                },
                "$set": {"updatedAt": now},
            },
            upsert=True
        )
        inserted += 1
    
    return {
        "ok": True,
        "seeds": DEFAULT_RU_CRYPTO_SEEDS,
        "inserted": inserted,
        "skipped": skipped,
        "total": len(DEFAULT_RU_CRYPTO_SEEDS),
    }

@telegram_router.post("/admin/discovery/full-pipeline")
async def admin_discovery_full_pipeline(request: Request):
    """
    Full discovery pipeline: fetch seeds -> ingest -> extract candidates -> evaluate
    POST /api/telegram-intel/admin/discovery/full-pipeline
    
    Steps:
    1. Import default seeds if not exists
    2. Fetch channel info via MTProto
    3. Fetch messages for each seed
    4. Extract mentions/forwards -> candidates
    5. Evaluate eligibility (crypto gate + RU/UA gate + members gate)
    6. Promote eligible to ingestion
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    body = await request.json() if request else {}
    limit = int(body.get("limit", 20))
    posts_per_seed = int(body.get("postsPerSeed", 200))
    
    now = datetime.now(timezone.utc)
    results = {
        "seeds_imported": 0,
        "seeds_fetched": 0,
        "posts_fetched": 0,
        "candidates_found": 0,
        "candidates_eligible": 0,
        "candidates_excluded": 0,
        "errors": [],
    }
    
    try:
        # Step 1: Import default seeds
        seed_result = await admin_import_default_seeds()
        results["seeds_imported"] = seed_result.get("inserted", 0)
        
        # Step 2-4: Fetch each seed and extract candidates
        seeds = await db.tg_channel_states.find(
            {"source": "SEED_DEFAULT"}
        ).limit(limit).to_list(limit)
        
        all_candidates = set()
        
        async with MTProtoConnection() as client:
            for seed in seeds:
                seed_username = seed.get("username")
                if not seed_username:
                    continue
                
                try:
                    # Fetch channel info
                    info = await client.get_channel_info(seed_username)
                    if info and 'error' not in info:
                        # Update seed in DB
                        await db.tg_channel_states.update_one(
                            {"username": seed_username},
                            {"$set": {
                                "title": info.get('title'),
                                "participantsCount": info.get('participantsCount'),
                                "isChannel": info.get('isChannel'),
                                "lastMtprotoFetch": now,
                                "stage": "QUALIFIED",
                            }}
                        )
                        results["seeds_fetched"] += 1
                    
                    # Fetch messages
                    messages = await client.get_channel_messages(seed_username, limit=posts_per_seed)
                    if messages:
                        results["posts_fetched"] += len(messages)
                        
                        # Save posts
                        for msg in messages:
                            await db.tg_posts.update_one(
                                {"username": seed_username, "messageId": msg['messageId']},
                                {"$set": {
                                    "username": seed_username,
                                    "messageId": msg['messageId'],
                                    "date": msg['date'],
                                    "text": msg.get('text', '')[:1000],
                                    "views": msg.get('views', 0),
                                    "forwards": msg.get('forwards', 0),
                                    "fetchedAt": now,
                                }},
                                upsert=True
                            )
                        
                        # Extract mentions
                        if DISCOVERY_LOADED:
                            for msg in messages:
                                text = msg.get('text', '')
                                found = extract_usernames(text) if 'extract_usernames' in dir() else []
                                # Also check for forwards
                                fwd_from = msg.get('forwardedFrom', '')
                                if fwd_from:
                                    found.append(fwd_from.lower())
                                
                                for candidate_u in found:
                                    if candidate_u and candidate_u != seed_username:
                                        all_candidates.add(candidate_u.lower())
                        
                except Exception as e:
                    results["errors"].append(f"{seed_username}: {str(e)[:50]}")
        
        results["candidates_found"] = len(all_candidates)
        
        # Step 5: Evaluate candidates
        min_crypto_score = 5  # Minimum crypto keywords
        
        for candidate_u in list(all_candidates)[:limit * 3]:  # Process more candidates
            try:
                # Check if already exists
                exists = await db.tg_channel_states.find_one({"username": candidate_u})
                if exists:
                    continue
                
                # Fetch candidate info
                async with MTProtoConnection() as client:
                    info = await client.get_channel_info(candidate_u)
                    
                    if not info or 'error' in info:
                        results["candidates_excluded"] += 1
                        continue
                    
                    members = info.get('participantsCount', 0)
                    
                    # Members gate: >= 1000
                    if members < 1000:
                        results["candidates_excluded"] += 1
                        await db.tg_channel_states.update_one(
                            {"username": candidate_u},
                            {"$set": {
                                "username": candidate_u,
                                "stage": "REJECTED",
                                "rejectReason": "MEMBERS_LT_1000",
                                "participantsCount": members,
                                "updatedAt": now,
                            }},
                            upsert=True
                        )
                        continue
                    
                    # Fetch posts for crypto/language gate
                    messages = await client.get_channel_messages(candidate_u, limit=50)
                    
                    if not messages:
                        results["candidates_excluded"] += 1
                        continue
                    
                    # Build text sample
                    sample_text = (info.get('about', '') or '') + '\n'
                    sample_text += '\n'.join([m.get('text', '') or '' for m in messages[:30]])
                    
                    # Crypto relevance gate
                    crypto_result = score_crypto_relevance_p1(sample_text)
                    if crypto_result["score"] < min_crypto_score:
                        results["candidates_excluded"] += 1
                        await db.tg_channel_states.update_one(
                            {"username": candidate_u},
                            {"$set": {
                                "username": candidate_u,
                                "stage": "REJECTED",
                                "rejectReason": "LOW_CRYPTO_RELEVANCE",
                                "participantsCount": members,
                                "cryptoRelevanceScore": crypto_result["score"],
                                "updatedAt": now,
                            }},
                            upsert=True
                        )
                        continue
                    
                    # Language gate (RU/UA only)
                    lang_result = score_language_ru_ua_p1(sample_text)
                    if lang_result["lang"] not in ["RU", "UA"]:
                        # Don't reject, just mark
                        pass  # Allow EN channels from crypto space
                    
                    # Check activity (last post <= 180 days)
                    last_post_at = None
                    if messages:
                        for msg in messages:
                            if msg.get('date'):
                                try:
                                    pd = datetime.fromisoformat(msg['date'].replace('Z', '+00:00'))
                                    if last_post_at is None or pd > last_post_at:
                                        last_post_at = pd
                                except:
                                    pass
                    
                    if last_post_at:
                        days_since = (now - last_post_at).days
                        if days_since > 180:
                            results["candidates_excluded"] += 1
                            await db.tg_channel_states.update_one(
                                {"username": candidate_u},
                                {"$set": {
                                    "username": candidate_u,
                                    "stage": "REJECTED",
                                    "rejectReason": "INACTIVE_180D",
                                    "participantsCount": members,
                                    "updatedAt": now,
                                }},
                                upsert=True
                            )
                            continue
                    
                    # ELIGIBLE! Save to database
                    results["candidates_eligible"] += 1
                    
                    await db.tg_channel_states.update_one(
                        {"username": candidate_u},
                        {"$set": {
                            "username": candidate_u,
                            "title": info.get('title'),
                            "participantsCount": members,
                            "isChannel": info.get('isChannel'),
                            "stage": "QUALIFIED",
                            "eligibility": {
                                "status": "ELIGIBLE",
                                "reasons": [],
                                "evaluatedAt": now,
                            },
                            "cryptoRelevanceScore": crypto_result["score"],
                            "lang": lang_result["lang"],
                            "lastPostAt": last_post_at,
                            "lastMtprotoFetch": now,
                            "updatedAt": now,
                        },
                        "$setOnInsert": {"createdAt": now}},
                        upsert=True
                    )
                    
                    # Save posts
                    for msg in messages:
                        await db.tg_posts.update_one(
                            {"username": candidate_u, "messageId": msg['messageId']},
                            {"$set": {
                                "username": candidate_u,
                                "messageId": msg['messageId'],
                                "date": msg['date'],
                                "text": msg.get('text', '')[:1000],
                                "views": msg.get('views', 0),
                                "forwards": msg.get('forwards', 0),
                                "fetchedAt": now,
                            }},
                            upsert=True
                        )
                    
                    # Compute metrics
                    if results["candidates_eligible"] >= limit:
                        break
                        
            except Exception as e:
                results["errors"].append(f"candidate {candidate_u}: {str(e)[:50]}")
        
        # Step 6: Recompute metrics
        await recompute_metrics(limit=100)
        
        return {
            "ok": True,
            "pipeline": "P1_DISCOVERY",
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"Discovery pipeline error: {e}")
        return {"ok": False, "error": str(e), "results": results}

@telegram_router.get("/admin/discovery/stats")
async def admin_discovery_stats():
    """
    Get discovery statistics
    GET /api/telegram-intel/admin/discovery/stats
    """
    try:
        # Stage breakdown
        stages = await db.tg_channel_states.aggregate([
            {"$group": {"_id": "$stage", "count": {"$sum": 1}}}
        ]).to_list(100)
        
        # Source breakdown
        sources = await db.tg_channel_states.aggregate([
            {"$group": {"_id": "$source", "count": {"$sum": 1}}}
        ]).to_list(100)
        
        # Rejection reasons
        rejections = await db.tg_channel_states.aggregate([
            {"$match": {"stage": "REJECTED"}},
            {"$group": {"_id": "$rejectReason", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]).to_list(100)
        
        # Eligibility breakdown
        eligibility = await db.tg_channel_states.aggregate([
            {"$match": {"eligibility.status": {"$exists": True}}},
            {"$group": {"_id": "$eligibility.status", "count": {"$sum": 1}}}
        ]).to_list(100)
        
        # Total posts and channels
        total_channels = await db.tg_channel_states.count_documents({})
        total_posts = await db.tg_posts.count_documents({})
        qualified = await db.tg_channel_states.count_documents({"stage": "QUALIFIED"})
        
        return {
            "ok": True,
            "summary": {
                "totalChannels": total_channels,
                "totalPosts": total_posts,
                "qualifiedChannels": qualified,
            },
            "byStage": {s["_id"]: s["count"] for s in stages if s["_id"]},
            "bySource": {s["_id"]: s["count"] for s in sources if s["_id"]},
            "byEligibility": {e["_id"]: e["count"] for e in eligibility if e["_id"]},
            "rejectionReasons": [{"reason": r["_id"], "count": r["count"]} for r in rejections if r["_id"]],
        }
    except Exception as e:
        logger.error(f"Discovery stats error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== G-1: Edge Extraction + Graph API ======================

import re
import hashlib

# Regex patterns for extracting Telegram mentions/links
TG_PATTERNS = [
    re.compile(r'@([a-zA-Z0-9_]{4,32})'),  # @username
    re.compile(r'(?:https?://)?t\.me/([a-zA-Z0-9_]{4,32})(?:/\d+)?'),  # t.me/username or t.me/username/123
    re.compile(r'tg://resolve\?domain=([a-zA-Z0-9_]{4,32})'),  # tg://resolve?domain=username
]

# Reserved/system paths to exclude
TG_RESERVED = {'joinchat', 'addstickers', 'share', 'socks', 'proxy', 'iv', 'c', 's', 'addtheme', 'setlanguage'}

def extract_mentions_from_text(text: str, source_username: str = None) -> list:
    """Extract all Telegram channel mentions from text"""
    if not text:
        return []
    
    mentions = set()
    for pattern in TG_PATTERNS:
        for match in pattern.finditer(text):
            username = match.group(1).lower()
            # Filter out reserved paths and self-references
            if username and username not in TG_RESERVED:
                if source_username and username == source_username.lower():
                    continue  # Skip self-mentions
                if len(username) >= 4:  # Telegram usernames are at least 4 chars
                    mentions.add(username)
    
    return list(mentions)

def generate_edge_hash(from_u: str, to_u: str, edge_type: str, message_id: int) -> str:
    """Generate idempotent hash for edge event"""
    key = f"{from_u}|{to_u}|{edge_type}|{message_id}"
    return hashlib.md5(key.encode()).hexdigest()

@telegram_router.post("/admin/edges/extract")
async def admin_extract_edges(request: Request):
    """
    Extract edges from all stored posts and save to tg_edge_events
    POST /api/telegram-intel/admin/edges/extract
    """
    body = await request.json() if request else {}
    limit = int(body.get("limit", 1000))
    channel_username = body.get("username")  # Optional: extract for specific channel
    
    now = datetime.now(timezone.utc)
    
    query = {}
    if channel_username:
        query["username"] = channel_username.lower()
    
    posts = await db.tg_posts.find(query).sort("date", -1).limit(limit).to_list(limit)
    
    extracted = 0
    duplicates = 0
    
    for post in posts:
        from_username = post.get("username", "").lower()
        text = post.get("text", "")
        message_id = post.get("messageId", 0)
        post_date = post.get("date")
        
        if not from_username or not text:
            continue
        
        # Extract mentions from text
        mentions = extract_mentions_from_text(text, from_username)
        
        for to_username in mentions:
            edge_hash = generate_edge_hash(from_username, to_username, "mention", message_id)
            
            try:
                result = await db.tg_edge_events.update_one(
                    {"hash": edge_hash},
                    {
                        "$setOnInsert": {
                            "hash": edge_hash,
                            "fromUsername": from_username,
                            "toUsername": to_username,
                            "type": "mention",
                            "messageId": message_id,
                            "date": post_date,
                            "weight": 1,
                            "createdAt": now,
                        }
                    },
                    upsert=True
                )
                if result.upserted_id:
                    extracted += 1
                else:
                    duplicates += 1
            except Exception as e:
                logger.warning(f"Edge insert error: {e}")
        
        # Check for forwards
        fwd_from = post.get("forwardedFrom", "")
        if fwd_from and fwd_from.lower() != from_username:
            fwd_username = fwd_from.lower()
            edge_hash = generate_edge_hash(from_username, fwd_username, "forward", message_id)
            
            try:
                result = await db.tg_edge_events.update_one(
                    {"hash": edge_hash},
                    {
                        "$setOnInsert": {
                            "hash": edge_hash,
                            "fromUsername": from_username,
                            "toUsername": fwd_username,
                            "type": "forward",
                            "messageId": message_id,
                            "date": post_date,
                            "weight": 1,
                            "createdAt": now,
                        }
                    },
                    upsert=True
                )
                if result.upserted_id:
                    extracted += 1
            except Exception as e:
                pass
    
    return {
        "ok": True,
        "postsProcessed": len(posts),
        "edgesExtracted": extracted,
        "duplicatesSkipped": duplicates,
    }

@telegram_router.post("/admin/edges/aggregate")
async def admin_aggregate_edges(request: Request):
    """
    Aggregate edge events into daily summaries
    POST /api/telegram-intel/admin/edges/aggregate
    """
    body = await request.json() if request else {}
    days_back = int(body.get("daysBack", 30))
    
    now = datetime.now(timezone.utc)
    start_date = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    
    # Calculate date range
    from datetime import timedelta
    end_date = start_date + timedelta(days=1)
    start_date = start_date - timedelta(days=days_back)
    
    # Aggregation pipeline
    pipeline = [
        {
            "$match": {
                "date": {"$gte": start_date.isoformat(), "$lt": end_date.isoformat()}
            }
        },
        {
            "$addFields": {
                "day": {"$substr": ["$date", 0, 10]}  # Extract YYYY-MM-DD
            }
        },
        {
            "$group": {
                "_id": {
                    "day": "$day",
                    "fromUsername": "$fromUsername",
                    "toUsername": "$toUsername",
                    "type": "$type"
                },
                "count": {"$sum": 1}
            }
        }
    ]
    
    results = await db.tg_edge_events.aggregate(pipeline).to_list(10000)
    
    upserted = 0
    for result in results:
        await db.tg_edges_daily.update_one(
            {
                "day": result["_id"]["day"],
                "fromUsername": result["_id"]["fromUsername"],
                "toUsername": result["_id"]["toUsername"],
                "type": result["_id"]["type"]
            },
            {
                "$set": {
                    "count": result["count"],
                    "updatedAt": now
                }
            },
            upsert=True
        )
        upserted += 1
    
    return {
        "ok": True,
        "aggregated": upserted,
        "dateRange": {
            "from": start_date.isoformat(),
            "to": end_date.isoformat()
        }
    }

@telegram_router.get("/graph")
async def get_graph(
    root: str = Query(None, description="Root channel username for ego-network"),
    days: int = Query(30, description="Days to include (7, 30, 90)"),
    edge_type: str = Query("all", description="Edge type: mention, forward, all"),
    min_weight: int = Query(1, description="Minimum edge weight to include"),
    limit_nodes: int = Query(100, description="Max nodes to return"),
    limit_links: int = Query(300, description="Max links to return"),
):
    """
    Get graph data for visualization
    GET /api/telegram-intel/graph
    
    Returns nodes and links for react-force-graph
    """
    try:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days)).strftime("%Y-%m-%d")
        
        # Build match filter
        match_filter = {"day": {"$gte": start_date}}
        if edge_type != "all":
            match_filter["type"] = edge_type
        
        # Get aggregated edges
        pipeline = [
            {"$match": match_filter},
            {
                "$group": {
                    "_id": {
                        "from": "$fromUsername",
                        "to": "$toUsername",
                        "type": "$type"
                    },
                    "weight": {"$sum": "$count"}
                }
            },
            {"$match": {"weight": {"$gte": min_weight}}},
            {"$sort": {"weight": -1}},
            {"$limit": limit_links * 2}  # Get more, we'll filter
        ]
        
        edges_raw = await db.tg_edges_daily.aggregate(pipeline).to_list(limit_links * 2)
        
        # If root specified, filter to ego-network
        if root:
            root_lower = root.lower()
            edges_raw = [
                e for e in edges_raw
                if e["_id"]["from"] == root_lower or e["_id"]["to"] == root_lower
            ]
        
        # Collect unique usernames
        usernames = set()
        links = []
        
        for edge in edges_raw[:limit_links]:
            from_u = edge["_id"]["from"]
            to_u = edge["_id"]["to"]
            usernames.add(from_u)
            usernames.add(to_u)
            
            links.append({
                "source": from_u,
                "target": to_u,
                "type": edge["_id"]["type"],
                "weight": edge["weight"]
            })
        
        # Get channel profiles for nodes
        channels = await db.tg_channel_states.find(
            {"username": {"$in": list(usernames)}}
        ).to_list(limit_nodes)
        
        channel_map = {c["username"]: c for c in channels}
        
        # Build nodes
        nodes = []
        for username in list(usernames)[:limit_nodes]:
            ch = channel_map.get(username, {})
            
            # Calculate node size based on members (log scale)
            members = ch.get("participantsCount", 1000) or 1000
            size = max(3, min(15, 3 + math.log10(max(1, members)) * 2))
            
            # Determine node type
            node_type = "channel"
            utility_score = ch.get("utilityScore", 50)
            
            nodes.append({
                "id": username,
                "label": ch.get("title", username)[:20],
                "type": node_type,
                "size": round(size, 1),
                "members": members,
                "avgReach": ch.get("avgReach", 0),
                "growth7": ch.get("growth7", 0),
                "utilityScore": utility_score,
                "avatarUrl": f"/api/telegram-intel/avatar/{username}" if ch else None,
            })
        
        # Calculate stats
        in_degree = {}
        out_degree = {}
        for link in links:
            out_degree[link["source"]] = out_degree.get(link["source"], 0) + link["weight"]
            in_degree[link["target"]] = in_degree.get(link["target"], 0) + link["weight"]
        
        # Find top hubs (most referenced)
        top_hubs = sorted(in_degree.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "ok": True,
            "nodes": nodes,
            "links": links,
            "stats": {
                "totalNodes": len(nodes),
                "totalLinks": len(links),
                "dateRange": {"from": start_date, "to": now.strftime("%Y-%m-%d")},
                "topHubs": [{"username": u, "inDegree": d} for u, d in top_hubs],
            }
        }
        
    except Exception as e:
        logger.error(f"Graph API error: {e}")
        return {"ok": False, "error": str(e), "nodes": [], "links": []}

@telegram_router.get("/graph/stats")
async def get_graph_stats():
    """
    Get graph statistics
    GET /api/telegram-intel/graph/stats
    """
    try:
        total_edges = await db.tg_edge_events.count_documents({})
        total_daily = await db.tg_edges_daily.count_documents({})
        
        # Get edge type breakdown
        type_stats = await db.tg_edge_events.aggregate([
            {"$group": {"_id": "$type", "count": {"$sum": 1}}}
        ]).to_list(10)
        
        # Get top sources (channels that mention most)
        top_sources = await db.tg_edge_events.aggregate([
            {"$group": {"_id": "$fromUsername", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]).to_list(10)
        
        # Get top targets (most mentioned channels)
        top_targets = await db.tg_edge_events.aggregate([
            {"$group": {"_id": "$toUsername", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10}
        ]).to_list(10)
        
        return {
            "ok": True,
            "totalEdgeEvents": total_edges,
            "totalDailyAggregates": total_daily,
            "byType": {t["_id"]: t["count"] for t in type_stats if t["_id"]},
            "topSources": [{"username": s["_id"], "count": s["count"]} for s in top_sources],
            "topTargets": [{"username": t["_id"], "count": t["count"]} for t in top_targets],
        }
    except Exception as e:
        logger.error(f"Graph stats error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/channel/{username}/snapshot")
async def get_channel_snapshot(
    username: str,
    days: int = Query(30, description="Window days (7, 30, 90)"),
):
    """
    Get channel snapshot with aggregated metrics
    GET /api/telegram-intel/channel/:username/snapshot?days=30
    """
    try:
        uname = normalize_username(username)
        if not uname:
            return {"ok": False, "error": "Invalid username"}
        
        # Try to get existing snapshot
        snapshot = await db.tg_channel_snapshots.find_one({
            'username': uname,
            'windowDays': days
        })
        
        # If no snapshot or too old (>6 hours), rebuild
        rebuild_needed = False
        if not snapshot:
            rebuild_needed = True
        elif snapshot.get('ts'):
            ts = snapshot['ts']
            # Handle naive datetime
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - ts
            if age.total_seconds() > 6 * 3600:  # 6 hours
                rebuild_needed = True
        
        if rebuild_needed:
            snapshot = await build_channel_snapshot(uname, days)
        
        if not snapshot:
            return {"ok": False, "error": "Channel not found or no data"}
        
        # Remove MongoDB _id
        snapshot.pop('_id', None)
        
        return {"ok": True, **snapshot}
        
    except Exception as e:
        logger.error(f"Channel snapshot error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/edge-events/rebuild/{username}")
async def admin_rebuild_edge_events(username: str):
    """
    Rebuild edge events from existing posts for a channel
    POST /api/telegram-intel/admin/edge-events/rebuild/:username
    """
    try:
        uname = normalize_username(username)
        if not uname:
            return {"ok": False, "error": "Invalid username"}
        
        # Get all posts for channel
        posts = await db.tg_posts.find({'username': uname}).to_list(10000)
        
        if not posts:
            return {"ok": False, "error": "No posts found", "count": 0}
        
        # Write edge events
        count = await write_edge_events(uname, posts)
        
        return {"ok": True, "username": uname, "postsProcessed": len(posts), "edgeEventsWritten": count}
        
    except Exception as e:
        logger.error(f"Edge events rebuild error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/snapshot/rebuild/{username}")
async def admin_rebuild_snapshot(username: str, days: int = Query(30)):
    """
    Rebuild channel snapshot
    POST /api/telegram-intel/admin/snapshot/rebuild/:username?days=30
    """
    try:
        uname = normalize_username(username)
        if not uname:
            return {"ok": False, "error": "Invalid username"}
        
        snapshot = await build_channel_snapshot(uname, days)
        
        if not snapshot:
            return {"ok": False, "error": "Channel not found or no data"}
        
        snapshot.pop('_id', None)
        return {"ok": True, **snapshot}
        
    except Exception as e:
        logger.error(f"Snapshot rebuild error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/channel/{username}/graph")
async def get_channel_graph(
    username: str,
    days: int = Query(30, description="Days to include (7, 30, 90)"),
    edge_type: str = Query("all", description="Edge type: mention, forward, all"),
    min_weight: int = Query(1, description="Minimum edge weight"),
    limit: int = Query(50, description="Max nodes"),
):
    """
    Get ego-network graph centered on a specific channel
    GET /api/telegram-intel/channel/:username/graph
    
    Uses tg_edge_events collection for real aggregated data
    """
    try:
        center = normalize_username(username)
        if not center:
            return {"ok": False, "error": "Invalid username", "nodes": [], "links": []}
        
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Get center channel profile
        center_channel = await db.tg_channel_states.find_one({"username": center})
        if not center_channel:
            return {"ok": False, "error": "Channel not found", "nodes": [], "links": []}
        
        # Build match filter for edge type
        type_filter = {}
        if edge_type != "all":
            type_filter["type"] = edge_type
        
        # Aggregate OUTGOING edges (center -> others)
        # Note: Edge events use fromUsername/toUsername fields
        outgoing_match = {"fromUsername": center, **type_filter}
        outgoing_agg = await db.tg_edge_events.aggregate([
            {"$match": outgoing_match},
            {"$group": {
                "_id": {"dst": "$toUsername", "type": "$type"},
                "weight": {"$sum": 1}
            }},
            {"$match": {"weight": {"$gte": min_weight}}},
            {"$sort": {"weight": -1}},
            {"$limit": limit}
        ]).to_list(limit)
        
        # Aggregate INCOMING edges (others -> center)
        incoming_match = {"toUsername": center, **type_filter}
        incoming_agg = await db.tg_edge_events.aggregate([
            {"$match": incoming_match},
            {"$group": {
                "_id": {"src": "$fromUsername", "type": "$type"},
                "weight": {"$sum": 1}
            }},
            {"$match": {"weight": {"$gte": min_weight}}},
            {"$sort": {"weight": -1}},
            {"$limit": limit}
        ]).to_list(limit)
        
        # Build nodes map
        usernames = {center}
        links = []
        outgoing = []
        incoming = []
        
        for o in outgoing_agg:
            dst = o["_id"]["dst"]
            usernames.add(dst)
            weight = o["weight"]
            edge_t = o["_id"]["type"]
            
            links.append({
                "source": center,
                "target": dst,
                "weight": weight,
                "edgeType": edge_t,
            })
            outgoing.append({"username": dst, "weight": weight, "type": edge_t})
        
        for i in incoming_agg:
            src = i["_id"]["src"]
            usernames.add(src)
            weight = i["weight"]
            edge_t = i["_id"]["type"]
            
            links.append({
                "source": src,
                "target": center,
                "weight": weight,
                "edgeType": edge_t,
            })
            incoming.append({"username": src, "weight": weight, "type": edge_t})
        
        # Get channel profiles for all usernames
        channels = await db.tg_channel_states.find(
            {"username": {"$in": list(usernames)}}
        ).to_list(limit + 10)
        
        channel_map = {c["username"]: c for c in channels}
        
        # Build nodes
        nodes = []
        for uname in list(usernames)[:limit]:
            ch = channel_map.get(uname, {})
            members = ch.get("participantsCount", 1000) or 1000
            
            # Node radius based on members (log scale)
            r = max(12, min(28, 8 + math.log10(max(1, members)) * 4))
            
            # Color based on utility score
            utility = ch.get("utilityScore", 50)
            if utility >= 75:
                color = "#10b981"  # emerald - high
            elif utility >= 55:
                color = "#3b82f6"  # blue - good
            elif utility >= 35:
                color = "#f59e0b"  # amber - medium
            else:
                color = "#94a3b8"  # slate - low
            
            is_center = uname == center
            
            nodes.append({
                "id": uname,
                "username": uname,
                "label": ch.get("title", uname)[:18] if not is_center else ch.get("title", uname)[:22],
                "isCenter": is_center,
                "r": r * 1.5 if is_center else r,
                "color": "#2563eb" if is_center else color,  # Blue for center
                "members": members,
                "avgReach": ch.get("avgReach", 0),
                "growth7": ch.get("growth7", 0),
                "utilityScore": utility,
                "activity": ch.get("activity", "MEDIUM"),
            })
        
        # Sort tables
        outgoing.sort(key=lambda x: x["weight"], reverse=True)
        incoming.sort(key=lambda x: x["weight"], reverse=True)
        
        # Bridges = channels that appear both in incoming and outgoing
        bridges = []
        outgoing_set = {o["username"] for o in outgoing[:15]}
        incoming_set = {i["username"] for i in incoming[:15]}
        for uname in outgoing_set & incoming_set:
            if uname == center:
                continue
            out_w = sum(o["weight"] for o in outgoing if o["username"] == uname)
            in_w = sum(i["weight"] for i in incoming if i["username"] == uname)
            bridges.append({"username": uname, "totalWeight": out_w + in_w})
        bridges.sort(key=lambda x: x["totalWeight"], reverse=True)
        
        return {
            "ok": True,
            "meta": {
                "center": center,
                "days": days,
                "minWeight": min_weight,
                "edgeType": edge_type,
                "totalNodes": len(nodes),
                "totalLinks": len(links),
            },
            "nodes": nodes,
            "links": links,
            "tables": {
                "topOutgoing": outgoing[:10],
                "topIncoming": incoming[:10],
                "bridges": bridges[:5],
            },
            "centerProfile": {
                "username": center,
                "title": center_channel.get("title", center),
                "members": center_channel.get("participantsCount", 0),
                "utilityScore": center_channel.get("utilityScore", 50),
                "growth7": center_channel.get("growth7", 0),
            }
        }
        
    except Exception as e:
        logger.error(f"Channel graph error: {e}")
        return {"ok": False, "error": str(e), "nodes": [], "links": []}

# ====================== Sector Classification Routes ======================

@telegram_router.get("/sectors/list")
async def list_all_sectors():
    """
    List all available sectors
    GET /api/telegram-intel/sectors/list
    """
    if SECTOR_CLASSIFIER_LOADED:
        return {
            "ok": True,
            "sectors": list_sectors()
        }
    return {"ok": False, "error": "Sector classifier not loaded"}

@telegram_router.get("/channel/{username}/sector")
async def get_channel_sector(username: str):
    """
    Get channel sector classification
    GET /api/telegram-intel/channel/:username/sector
    """
    clean_username = normalize_username(username)
    
    # Get from database
    channel = await db.tg_channel_states.find_one(
        {"username": clean_username},
        {"sector": 1, "sectorSecondary": 1, "sectorScores": 1, "sectorConfidence": 1, "sectorColor": 1, "tags": 1}
    )
    
    if not channel:
        return {"ok": False, "error": "Channel not found"}
    
    return {
        "ok": True,
        "username": clean_username,
        "sector": channel.get("sector"),
        "secondary": channel.get("sectorSecondary", []),
        "scores": channel.get("sectorScores", {}),
        "confidence": channel.get("sectorConfidence", 0),
        "color": channel.get("sectorColor"),
        "tags": channel.get("tags", []),
    }

@telegram_router.post("/admin/sector/classify/{username}")
async def classify_channel_sector_route(username: str):
    """
    Classify channel sector
    POST /api/telegram-intel/admin/sector/classify/:username
    """
    if not SECTOR_CLASSIFIER_LOADED:
        return {"ok": False, "error": "Sector classifier not loaded"}
    
    clean_username = normalize_username(username)
    
    try:
        result = await classify_and_save_sector(db, clean_username)
        if result:
            return {
                "ok": True,
                "username": clean_username,
                **result
            }
        return {"ok": False, "error": "Channel not found"}
    except Exception as e:
        logger.error(f"Sector classification error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/sector/batch-classify")
async def batch_classify_sectors_route(limit: int = 100):
    """
    Batch classify sectors for channels without classification
    POST /api/telegram-intel/admin/sector/batch-classify
    """
    if not SECTOR_CLASSIFIER_LOADED:
        return {"ok": False, "error": "Sector classifier not loaded"}
    
    try:
        result = await batch_classify_sectors(db, limit)
        return {"ok": True, **result}
    except Exception as e:
        logger.error(f"Batch sector classification error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.get("/sectors/channels")
async def get_channels_by_sector(
    sector: Optional[str] = None,
    limit: int = 25,
    page: int = 1
):
    """
    Get channels filtered by sector
    GET /api/telegram-intel/sectors/channels?sector=DeFi
    """
    filter_query = {"participantsCount": {"$gte": 1000}}
    
    if sector:
        filter_query["sector"] = sector
    
    skip = (page - 1) * limit
    
    channels = await db.tg_channel_states.find(
        filter_query,
        {"_id": 0, "username": 1, "title": 1, "participantsCount": 1, "sector": 1, "sectorColor": 1, "tags": 1, "avatarUrl": 1}
    ).sort("participantsCount", -1).skip(skip).limit(limit).to_list(limit)
    
    total = await db.tg_channel_states.count_documents(filter_query)
    
    return {
        "ok": True,
        "items": channels,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": math.ceil(total / limit) if total > 0 else 1
    }

# ====================== Avatar Refresh Helper ======================

async def refresh_channel_avatar(mtproto_client, username: str) -> Optional[str]:
    """
    Helper function to refresh channel avatar via MTProto.
    Used by scheduler for automatic avatar updates.
    """
    clean_username = normalize_username(username)
    
    try:
        avatar_url = await mtproto_client.download_profile_photo(clean_username)
        return avatar_url
    except Exception as e:
        logger.warning(f"Avatar refresh failed for {clean_username}: {e}")
        return None

@telegram_router.post("/admin/avatar/refresh/{username}")
async def admin_refresh_avatar(username: str):
    """
    Manually refresh channel avatar
    POST /api/telegram-intel/admin/avatar/refresh/:username
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    clean_username = normalize_username(username)
    
    try:
        async with MTProtoConnection() as client:
            avatar_url = await client.download_profile_photo(clean_username)
            
            if avatar_url:
                await db.tg_channel_states.update_one(
                    {"username": clean_username},
                    {"$set": {"avatarUrl": avatar_url, "avatarUpdatedAt": datetime.utcnow()}}
                )
                return {
                    "ok": True,
                    "username": clean_username,
                    "avatarUrl": avatar_url
                }
            return {"ok": False, "error": "No avatar available"}
    except Exception as e:
        logger.error(f"Avatar refresh error: {e}")
        return {"ok": False, "error": str(e)}

@telegram_router.post("/admin/avatar/batch-refresh")
async def batch_refresh_avatars(limit: int = 20):
    """
    Batch refresh avatars for channels with old or missing avatars
    POST /api/telegram-intel/admin/avatar/batch-refresh
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    # Get channels with old or missing avatars
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    channels = await db.tg_channel_states.find(
        {
            "$or": [
                {"avatarUrl": {"$exists": False}},
                {"avatarUrl": None},
                {"avatarUpdatedAt": {"$lt": one_week_ago}},
                {"avatarUpdatedAt": {"$exists": False}},
            ],
            "participantsCount": {"$gte": 1000}
        },
        {"username": 1}
    ).limit(limit).to_list(limit)
    
    results = []
    
    try:
        async with MTProtoConnection() as client:
            for ch in channels:
                username = ch.get("username")
                if not username:
                    continue
                
                try:
                    avatar_url = await client.download_profile_photo(username)
                    if avatar_url:
                        await db.tg_channel_states.update_one(
                            {"username": username},
                            {"$set": {"avatarUrl": avatar_url, "avatarUpdatedAt": datetime.utcnow()}}
                        )
                        results.append({"username": username, "ok": True, "avatarUrl": avatar_url})
                    else:
                        results.append({"username": username, "ok": False, "error": "No avatar"})
                except Exception as e:
                    results.append({"username": username, "ok": False, "error": str(e)})
                
                # Small delay to avoid rate limits
                await asyncio.sleep(0.5)
        
        return {
            "ok": True,
            "processed": len(results),
            "successful": len([r for r in results if r.get("ok")]),
            "results": results
        }
    except Exception as e:
        logger.error(f"Batch avatar refresh error: {e}")
        return {"ok": False, "error": str(e)}

# ====================== Full Sync Endpoint ======================

@telegram_router.post("/admin/sync/full")
async def full_sync_all_channels():
    """
    Full synchronization of all tracked channels:
    1. Fetch latest messages for each channel
    2. Rebuild snapshots
    3. Extract network edges
    4. Classify sectors
    
    POST /api/telegram-intel/admin/sync/full
    """
    if not MTPROTO_AVAILABLE:
        return {"ok": False, "error": "MTProto not available"}
    
    try:
        # Get all tracked channels
        channels = await db.tg_channel_states.find(
            {"participantsCount": {"$gte": 1000}},
            {"username": 1}
        ).to_list(100)
        
        if not channels:
            return {"ok": True, "message": "No channels to sync", "processed": 0}
        
        results = []
        
        async with MTProtoConnection() as client:
            for ch in channels:
                username = ch.get("username")
                if not username:
                    continue
                
                channel_result = {
                    "username": username,
                    "messages": 0,
                    "snapshot": False,
                    "edges": 0,
                    "sector": None,
                    "errors": []
                }
                
                try:
                    # 1. Fetch messages
                    messages = await client.get_channel_messages(username, limit=50)
                    if messages:
                        now = datetime.now(timezone.utc)
                        for msg in messages:
                            await db.tg_posts.update_one(
                                {"username": username.lower(), "messageId": msg['messageId']},
                                {"$set": {
                                    "username": username.lower(),
                                    "messageId": msg['messageId'],
                                    "date": msg['date'],
                                    "text": (msg.get('text') or '')[:1000],
                                    "views": msg.get('views', 0),
                                    "forwards": msg.get('forwards', 0),
                                    "hasMedia": msg.get('hasMedia', False),
                                    "fetchedAt": now,
                                }},
                                upsert=True
                            )
                        channel_result["messages"] = len(messages)
                    
                    # 2. Rebuild snapshot
                    snapshot = await build_channel_snapshot(username, 30)
                    channel_result["snapshot"] = snapshot is not None
                    
                    # 3. Extract edges
                    if NETWORK_LOADED:
                        try:
                            posts = await db.tg_posts.find({"username": username.lower()}).to_list(100)
                            edges_written = await write_edge_events(username, posts)
                            channel_result["edges"] = edges_written or 0
                        except:
                            pass
                    
                    # 4. Classify sector
                    if SECTOR_CLASSIFIER_LOADED:
                        try:
                            sector_result = await classify_and_save_sector(db, username)
                            channel_result["sector"] = sector_result.get("primary") if sector_result else None
                        except:
                            pass
                    
                except Exception as e:
                    channel_result["errors"].append(str(e)[:100])
                
                results.append(channel_result)
                
                # Small delay between channels
                await asyncio.sleep(1)
        
        return {
            "ok": True,
            "processed": len(results),
            "results": results,
        }
        
    except Exception as e:
        logger.error(f"Full sync error: {e}")
        return {"ok": False, "error": str(e)}


# Background task for auto-sync on startup
_startup_sync_done = False

async def startup_sync_task():
    """Run full sync on startup (once)"""
    global _startup_sync_done
    if _startup_sync_done:
        return
    
    _startup_sync_done = True
    
    # Wait for services to be ready
    await asyncio.sleep(5)
    
    try:
        logger.info("Starting automatic channel sync...")
        
        # Check if MTProto is available
        if not MTPROTO_AVAILABLE:
            logger.warning("MTProto not available, skipping auto-sync")
            return
        
        # Get channels that need sync (no recent posts)
        since = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        channels = await db.tg_channel_states.find(
            {"participantsCount": {"$gte": 1000}},
            {"username": 1}
        ).to_list(50)
        
        if not channels:
            logger.info("No channels to sync on startup")
            return
        
        synced = 0
        async with MTProtoConnection() as client:
            for ch in channels:
                username = ch.get("username")
                if not username:
                    continue
                
                # Check if already has recent posts
                recent_post = await db.tg_posts.find_one({
                    "username": username.lower(),
                    "date": {"$gte": since}
                })
                
                if recent_post:
                    continue  # Already has recent data
                
                try:
                    # Fetch messages
                    messages = await client.get_channel_messages(username, limit=50)
                    if messages:
                        now = datetime.now(timezone.utc)
                        for msg in messages:
                            await db.tg_posts.update_one(
                                {"username": username.lower(), "messageId": msg['messageId']},
                                {"$set": {
                                    "username": username.lower(),
                                    "messageId": msg['messageId'],
                                    "date": msg['date'],
                                    "text": (msg.get('text') or '')[:1000],
                                    "views": msg.get('views', 0),
                                    "forwards": msg.get('forwards', 0),
                                    "hasMedia": msg.get('hasMedia', False),
                                    "fetchedAt": now,
                                }},
                                upsert=True
                            )
                        
                        # Build snapshot
                        await build_channel_snapshot(username, 30)
                        synced += 1
                        logger.info(f"Auto-synced {username}: {len(messages)} messages")
                    
                    await asyncio.sleep(2)  # Rate limiting
                    
                except Exception as e:
                    logger.warning(f"Auto-sync error for {username}: {e}")
        
        logger.info(f"Startup sync completed: {synced} channels synced")
        
    except Exception as e:
        logger.error(f"Startup sync task error: {e}")


@app.on_event("startup")
async def startup_event():
    """Run startup tasks"""
    # Start background sync task
    asyncio.create_task(startup_sync_task())
    
    # Initialize Task 1-4 indexes
    try:
        if MEDIA_ENGINE_AVAILABLE:
            await ensure_media_indexes(db)
        if SCHEDULER_V2_AVAILABLE:
            await ensure_scheduler_indexes(db)
        if AUTH_ACTOR_AVAILABLE:
            await ensure_auth_indexes(db)
            # Migrate legacy watchlist (one-time)
            await migrate_legacy_watchlist(db)
        if DELIVERY_BOT_AVAILABLE:
            await ensure_delivery_indexes(db)
        logger.info("Task 1-4 indexes initialized")
    except Exception as e:
        logger.error(f"Index initialization error: {e}")
    
    # Initialize Geo Intel Module
    if GEO_INTEL_AVAILABLE:
        try:
            geo_module = GeoModule(db)
            await geo_module.start()
            app.include_router(geo_module.router)
            logger.info("Geo Intel module initialized")
        except Exception as e:
            logger.error(f"Geo Intel initialization error: {e}")
    
    # Initialize Geo Admin Module
    if GEO_ADMIN_AVAILABLE:
        try:
            admin_router = build_admin_router(db)
            app.include_router(admin_router)
            logger.info("Geo Admin module initialized")
        except Exception as e:
            logger.error(f"Geo Admin initialization error: {e}")
    
    # Initialize Signal Intelligence Module
    try:
        from signal_intel.router import create_signal_router
        signal_router = create_signal_router(db)
        app.include_router(signal_router)
        logger.info("Signal Intelligence module initialized")
    except Exception as e:
        logger.error(f"Signal Intelligence initialization error: {e}")


# Include routers
app.include_router(api_router)
app.include_router(telegram_router)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
