"""
Signal Intelligence Router - API endpoints for signal processing
"""
from fastapi import APIRouter, Depends, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from .engine import SignalAIEngine, SIGNAL_TYPES
from .slang import SlangNormalizer, SIGNAL_KEYWORDS, DEFAULT_SLANG_MAP

logger = logging.getLogger(__name__)


def create_signal_router(db) -> APIRouter:
    """Create Signal Intelligence router with database connection"""
    
    router = APIRouter(prefix="/api/signal-intel", tags=["signal-intel"])
    
    # Initialize engine (lazy)
    engine: SignalAIEngine = None
    
    async def get_engine() -> SignalAIEngine:
        nonlocal engine
        if engine is None:
            engine = SignalAIEngine(db)
            await engine.initialize()
        return engine
    
    # ==================== Health ====================
    
    @router.get("/health")
    async def health():
        """Signal Intelligence health check"""
        eng = await get_engine()
        return {
            "ok": True,
            "module": "signal-intel",
            "aiEnabled": eng.ai_enabled,
            "confidenceThreshold": eng.confidence_threshold,
            "signalTypes": list(SIGNAL_TYPES.keys())
        }
    
    # ==================== Signal Processing ====================
    
    @router.post("/process")
    async def process_text(body: Dict[str, Any] = Body(...)):
        """
        Process text and extract signals (without saving)
        POST /api/signal-intel/process
        Body: { text: string, channel?: string }
        """
        text = body.get("text", "")
        channel = body.get("channel")
        
        if not text:
            return {"ok": False, "error": "No text provided"}
        
        eng = await get_engine()
        signals = await eng.process_post(text, channel)
        
        return {
            "ok": True,
            "count": len(signals),
            "signals": signals
        }
    
    @router.post("/process-and-save")
    async def process_and_save(body: Dict[str, Any] = Body(...)):
        """
        Process text, extract signals, and save to database
        POST /api/signal-intel/process-and-save
        Body: { text: string, channel?: string }
        """
        text = body.get("text", "")
        channel = body.get("channel")
        
        if not text:
            return {"ok": False, "error": "No text provided"}
        
        eng = await get_engine()
        result = await eng.process_and_save_post(text, channel)
        
        return {
            "ok": True,
            **result
        }
    
    @router.post("/analyze-line")
    async def analyze_line(body: Dict[str, Any] = Body(...)):
        """
        Analyze single line of text
        POST /api/signal-intel/analyze-line
        Body: { text: string }
        """
        text = body.get("text", "")
        
        if not text:
            return {"ok": False, "error": "No text provided"}
        
        eng = await get_engine()
        signal = await eng.process_line(text)
        
        return {
            "ok": True,
            "signal": signal
        }
    
    # ==================== Active Signals ====================
    
    @router.get("/signals")
    async def get_signals(hours: int = Query(2, ge=1, le=24)):
        """Get active signals"""
        eng = await get_engine()
        signals = await eng.get_active_signals(hours)
        
        return {
            "ok": True,
            "count": len(signals),
            "signals": signals
        }
    
    @router.delete("/signals/expired")
    async def cleanup_expired():
        """Remove expired signals"""
        eng = await get_engine()
        deleted = await eng.cleanup_expired()
        
        return {
            "ok": True,
            "deleted": deleted
        }
    
    # ==================== Slang Dictionary ====================
    
    @router.get("/slang")
    async def get_slang():
        """Get slang dictionary"""
        # Combine default + custom
        custom = {}
        async for doc in db.slang_dictionary.find({}, {"_id": 0}):
            custom[doc["word"]] = doc["meaning"]
        
        return {
            "ok": True,
            "default": DEFAULT_SLANG_MAP,
            "custom": custom,
            "total": len(DEFAULT_SLANG_MAP) + len(custom)
        }
    
    @router.post("/slang")
    async def add_slang(body: Dict[str, Any] = Body(...)):
        """Add custom slang word"""
        word = body.get("word", "").lower().strip()
        meaning = body.get("meaning", "").strip()
        
        if not word or not meaning:
            return {"ok": False, "error": "Word and meaning required"}
        
        await db.slang_dictionary.update_one(
            {"word": word},
            {
                "$set": {
                    "word": word,
                    "meaning": meaning,
                    "updatedAt": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        # Update engine's normalizer
        eng = await get_engine()
        eng.normalizer.add_slang(word, meaning)
        
        return {"ok": True, "word": word, "meaning": meaning}
    
    @router.delete("/slang/{word}")
    async def delete_slang(word: str):
        """Delete custom slang word"""
        result = await db.slang_dictionary.delete_one({"word": word.lower()})
        return {"ok": True, "deleted": result.deleted_count > 0}
    
    # ==================== Signal Types ====================
    
    @router.get("/types")
    async def get_signal_types():
        """Get signal type configurations"""
        return {
            "ok": True,
            "types": SIGNAL_TYPES,
            "keywords": SIGNAL_KEYWORDS
        }
    
    # ==================== AI Settings ====================
    
    @router.get("/settings")
    async def get_settings():
        """Get AI settings"""
        settings = await db.system_settings.find_one({"key": "ai_settings"})
        
        if settings and settings.get("value"):
            config = settings["value"]
            # Don't expose full API key
            if config.get("openai_key"):
                config["openai_key_set"] = True
                config["openai_key"] = config["openai_key"][:8] + "..." if len(config["openai_key"]) > 8 else "***"
            return {"ok": True, "settings": config}
        
        return {
            "ok": True,
            "settings": {
                "enabled": False,
                "openai_key_set": False,
                "model": "gpt-4o-mini",
                "confidence_threshold": 0.6
            }
        }
    
    @router.post("/settings")
    async def save_settings(body: Dict[str, Any] = Body(...)):
        """Save AI settings"""
        config = {
            "enabled": body.get("enabled", False),
            "model": body.get("model", "gpt-4o-mini"),
            "confidence_threshold": float(body.get("confidence_threshold", 0.6)),
            "updatedAt": datetime.now(timezone.utc)
        }
        
        # Only update key if provided
        if body.get("openai_key"):
            config["openai_key"] = body["openai_key"]
        else:
            # Keep existing key
            existing = await db.system_settings.find_one({"key": "ai_settings"})
            if existing and existing.get("value", {}).get("openai_key"):
                config["openai_key"] = existing["value"]["openai_key"]
        
        await db.system_settings.update_one(
            {"key": "ai_settings"},
            {"$set": {"key": "ai_settings", "value": config}},
            upsert=True
        )
        
        # Reinitialize engine
        nonlocal engine
        engine = None
        
        return {"ok": True, "saved": True}
    
    # ==================== Batch Processing ====================
    
    @router.post("/batch/channel/{username}")
    async def process_channel_posts(username: str, limit: int = Query(50, ge=1, le=200)):
        """
        Process posts from a channel and extract signals
        POST /api/signal-intel/batch/channel/:username
        """
        # Get posts from tg_posts
        cursor = db.tg_posts.find(
            {"username": username.lower()},
            {"_id": 0, "text": 1, "messageId": 1, "date": 1}
        ).sort("date", -1).limit(limit)
        
        posts = await cursor.to_list(length=limit)
        
        if not posts:
            return {"ok": False, "error": "No posts found for channel"}
        
        eng = await get_engine()
        
        total_signals = 0
        total_saved = 0
        all_signals = []
        
        for post in posts:
            if post.get("text"):
                result = await eng.process_and_save_post(post["text"], username)
                total_signals += result["processed"]
                total_saved += result["saved"]
                all_signals.extend(result["signals"])
        
        return {
            "ok": True,
            "channel": username,
            "postsProcessed": len(posts),
            "signalsExtracted": total_signals,
            "signalsSaved": total_saved,
            "signals": all_signals[:20]  # Return sample
        }
    
    return router
