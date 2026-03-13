"""
Signal Classifier - AI-powered signal classification
"""
import os
import json
import hashlib
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Signal types with TTL in minutes
SIGNAL_TYPES = {
    "police": {"ttl": 30, "icon": "police", "color": "#3B82F6"},
    "detention": {"ttl": 45, "icon": "detention", "color": "#EF4444"},
    "checkpoint": {"ttl": 60, "icon": "checkpoint", "color": "#F59E0B"},
    "raid": {"ttl": 45, "icon": "raid", "color": "#8B5CF6"},
    "tck": {"ttl": 45, "icon": "tck", "color": "#10B981"},
    "weather": {"ttl": 20, "icon": "weather", "color": "#6B7280"},
    "safe": {"ttl": 15, "icon": "safe", "color": "#22C55E"},
    "trash": {"ttl": 5, "icon": "trash", "color": "#9CA3AF"},
}

SYSTEM_PROMPT = """You are an AI that extracts urban security signals from Ukrainian/Russian Telegram messages.

IMPORTANT: Messages often contain slang. Common slang:
- "сині", "баклажани", "менти" = police
- "зелені", "гуси", "тцк" = military recruitment patrols
- "бп", "блокпост" = checkpoint
- "пакують", "забрали", "зупинили" = detention
- "облава", "пасутся", "выскакивают" = raid/search

Return ONLY valid JSON with these exact fields:
{
  "type": "police|detention|checkpoint|raid|tck|weather|safe|trash",
  "location": "extracted location or null",
  "confidence": 0.0-1.0,
  "description": "brief description in English"
}

Signal types:
- police: Police patrol or presence
- detention: Someone being stopped/detained
- checkpoint: Blockpost or checkpoint
- raid: Active raid or search operation  
- tck: Military recruitment patrol (TCK)
- weather: Weather warning
- safe: Area reported as clear/safe
- trash: Not a signal, irrelevant

Rules:
1. If message says "вільно", "чисто", "свободно" → type: "safe"
2. If can't determine type → type: "trash", confidence < 0.3
3. All locations are in Kyiv/Ukraine region
4. Extract street names, districts, metro stations as location
5. Be conservative with confidence - only high if clear signal"""

USER_PROMPT_TEMPLATE = """Extract signal from this message:

{text}

Return JSON only."""


class SignalClassifier:
    """AI-powered signal classifier using OpenAI"""
    
    def __init__(self, db=None):
        self.db = db
        self.openai_client = None
        self.api_key = None
        self.model = "gpt-4o-mini"
        self.confidence_threshold = 0.6
        self.ai_enabled = True
    
    async def initialize(self):
        """Initialize with settings from database"""
        if self.db:
            try:
                settings = await self.db.system_settings.find_one({"key": "ai_settings"})
                if settings and settings.get("value"):
                    config = settings["value"]
                    self.api_key = config.get("openai_key")
                    self.model = config.get("model", "gpt-4o-mini")
                    self.confidence_threshold = config.get("confidence_threshold", 0.6)
                    self.ai_enabled = config.get("enabled", True)
                    
                    if self.api_key:
                        await self._init_client()
            except Exception as e:
                logger.error(f"Failed to load AI settings: {e}")
    
    async def _init_client(self):
        """Initialize OpenAI client"""
        try:
            from openai import AsyncOpenAI
            self.openai_client = AsyncOpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized")
        except ImportError:
            logger.warning("OpenAI package not installed")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")
    
    def set_api_key(self, key: str):
        """Set API key dynamically"""
        self.api_key = key
    
    async def _get_cached(self, text_hash: str) -> Optional[Dict]:
        """Check cache for previous classification"""
        if self.db is None:
            return None
        
        try:
            cached = await self.db.ai_cache.find_one({"hash": text_hash})
            if cached:
                return cached.get("result")
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
        
        return None
    
    async def _save_cache(self, text_hash: str, text: str, result: Dict):
        """Save classification to cache"""
        if self.db is None:
            return
        
        try:
            await self.db.ai_cache.update_one(
                {"hash": text_hash},
                {
                    "$set": {
                        "hash": text_hash,
                        "text": text[:500],
                        "result": result,
                        "createdAt": datetime.now(timezone.utc)
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Cache save error: {e}")
    
    async def classify(self, text: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Classify text using AI
        Returns: {type, location, confidence, description}
        """
        if not text or len(text.strip()) < 5:
            return {"type": "trash", "location": None, "confidence": 0.1, "description": "Text too short"}
        
        # Generate hash for caching
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        # Check cache first
        if use_cache:
            cached = await self._get_cached(text_hash)
            if cached:
                cached["cached"] = True
                return cached
        
        # If AI not enabled or no client, return unknown
        if not self.ai_enabled or not self.openai_client:
            return {
                "type": "unknown",
                "location": None,
                "confidence": 0.0,
                "description": "AI not configured",
                "ai_used": False
            }
        
        try:
            response = await self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_PROMPT_TEMPLATE.format(text=text)}
                ],
                temperature=0.1,
                max_tokens=200
            )
            
            content = response.choices[0].message.content.strip()
            
            # Parse JSON from response
            # Handle markdown code blocks
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            
            result = json.loads(content)
            
            # Validate and normalize result
            result = self._normalize_result(result)
            result["ai_used"] = True
            result["cached"] = False
            
            # Save to cache
            await self._save_cache(text_hash, text, result)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response: {e}")
            return {
                "type": "unknown",
                "location": None,
                "confidence": 0.0,
                "description": "AI response parse error",
                "ai_used": True,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"AI classification error: {e}")
            return {
                "type": "unknown",
                "location": None,
                "confidence": 0.0,
                "description": str(e),
                "ai_used": True,
                "error": str(e)
            }
    
    def _normalize_result(self, result: Dict) -> Dict:
        """Normalize AI result to expected format"""
        normalized = {
            "type": result.get("type", "unknown"),
            "location": result.get("location"),
            "confidence": float(result.get("confidence", 0.5)),
            "description": result.get("description", "")
        }
        
        # Validate type
        if normalized["type"] not in SIGNAL_TYPES:
            normalized["type"] = "unknown"
        
        # Clamp confidence
        normalized["confidence"] = max(0.0, min(1.0, normalized["confidence"]))
        
        return normalized
    
    def get_signal_config(self, signal_type: str) -> Dict:
        """Get configuration for signal type"""
        return SIGNAL_TYPES.get(signal_type, SIGNAL_TYPES["trash"])
    
    async def batch_classify(self, texts: List[str]) -> List[Dict]:
        """Classify multiple texts"""
        results = []
        for text in texts:
            result = await self.classify(text)
            results.append(result)
        return results
