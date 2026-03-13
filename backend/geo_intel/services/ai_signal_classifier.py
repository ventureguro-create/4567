"""
AI Signal Classifier v2.0 - Advanced Text Classification

Uses OpenAI GPT-4o-mini to classify Ukrainian/Russian text messages into signal types.
Integrated with Event Builder for deduplication and correlation.

Features:
- Multi-language support (UA, RU, EN)
- Location extraction with multiple mentions
- Slang normalization
- Confidence scoring
- Entity extraction (vehicle, color, direction)
- Negative message detection

Pipeline:
    Raw Text → Slang Normalizer → AI Classifier → Location Extractor → Event Builder

Signal Types:
- checkpoint (БП, блокпост)
- police (поліція, ДПС)
- detention (облава, забирають)
- raid (рейд)
- danger (небезпека)
- fire (пожежа)
- accident (ДТП)
- weather/rain (погода, дощ)
- virus (захворювання)
- trash (сміття)
"""
import logging
import os
import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# =============================================================================
# SIGNAL TYPES CONFIGURATION
# =============================================================================

SIGNAL_TYPES = {
    "checkpoint": {
        "emoji": "🚧",
        "priority": 0.80,
        "ttl_minutes": 60,
        "keywords_ua": ["блокпост", "бп", "стоять", "перевіряють", "тормозять", "зупиняють"],
        "keywords_ru": ["блокпост", "бп", "стоят", "проверяют", "тормозят", "останавливают"],
    },
    "police": {
        "emoji": "🚔",
        "priority": 0.75,
        "ttl_minutes": 45,
        "keywords_ua": ["поліція", "полісмен", "даі", "патруль", "гаішник", "мент", "копи"],
        "keywords_ru": ["полиция", "полицейский", "дпс", "гаи", "патруль", "гаишник", "мент", "копы"],
    },
    "detention": {
        "emoji": "⚠️",
        "priority": 0.90,
        "ttl_minutes": 120,
        "keywords_ua": ["забирають", "вручають", "повістки", "тцк", "облава", "хапають", "ловлять"],
        "keywords_ru": ["забирают", "вручают", "повестки", "тцк", "облава", "хватают", "ловят"],
    },
    "raid": {
        "emoji": "🔴",
        "priority": 0.85,
        "ttl_minutes": 90,
        "keywords_ua": ["рейд", "масова", "перевірка", "документи"],
        "keywords_ru": ["рейд", "массовая", "проверка", "документы"],
    },
    "danger": {
        "emoji": "🚨",
        "priority": 0.85,
        "ttl_minutes": 60,
        "keywords_ua": ["небезпека", "обережно", "увага", "небезпечно"],
        "keywords_ru": ["опасность", "осторожно", "внимание", "опасно"],
    },
    "fire": {
        "emoji": "🔥",
        "priority": 0.90,
        "ttl_minutes": 90,
        "keywords_ua": ["пожежа", "горить", "вогонь", "дим"],
        "keywords_ru": ["пожар", "горит", "огонь", "дым"],
    },
    "accident": {
        "emoji": "💥",
        "priority": 0.75,
        "ttl_minutes": 60,
        "keywords_ua": ["дтп", "аварія", "зіткнення", "перекинувся"],
        "keywords_ru": ["дтп", "авария", "столкновение", "перевернулся"],
    },
    "weather": {
        "emoji": "🌧️",
        "priority": 0.50,
        "ttl_minutes": 180,
        "keywords_ua": ["дощ", "злива", "гроза", "потоп", "град"],
        "keywords_ru": ["дождь", "ливень", "гроза", "потоп", "град"],
    },
    "virus": {
        "emoji": "☣️",
        "priority": 0.70,
        "ttl_minutes": 120,
        "keywords_ua": ["вірус", "хвороба", "епідемія", "карантин"],
        "keywords_ru": ["вирус", "болезнь", "эпидемия", "карантин"],
    },
    "trash": {
        "emoji": "🗑️",
        "priority": 0.40,
        "ttl_minutes": 480,
        "keywords_ua": ["сміття", "звалище", "смердить"],
        "keywords_ru": ["мусор", "свалка", "воняет"],
    },
    "flood": {
        "emoji": "🌊",
        "priority": 0.70,
        "ttl_minutes": 240,
        "keywords_ua": ["затоплення", "підтоплення", "вода"],
        "keywords_ru": ["затопление", "подтопление", "вода"],
    },
}

# =============================================================================
# SLANG DICTIONARY
# =============================================================================

SLANG_DICTIONARY = {
    # Ukrainian slang
    "бп": "блокпост",
    "тцк": "територіальний центр комплектування",
    "копи": "поліція",
    "мент": "поліція",
    "менти": "поліція",
    "хапають": "затримують",
    "ловлять": "затримують",
    "шмонають": "перевіряють документи",
    # Russian slang
    "гаи": "полиция",
    "дпс": "полиция",
    "гаишники": "полиция",
    "хватают": "задерживают",
    "ловят": "задерживают",
    # Abbreviations
    "дтп": "дорожньо-транспортна пригода",
}

# =============================================================================
# NEGATIVE KEYWORDS
# =============================================================================

NEGATIVE_KEYWORDS = [
    # Ukrainian
    "чисто", "вільно", "пусто", "розійшлись", "немає", "нема", "проїхали",
    "зняли", "забрали", "поїхали", "закінчилось", "все ок", "все гаразд",
    # Russian  
    "чисто", "свободно", "пусто", "разошлись", "нету", "нет", "уехали",
    "сняли", "убрали", "закончилось", "всё ок", "всё хорошо",
    # English
    "clear", "empty", "gone", "left", "removed", "finished", "all good",
]

# =============================================================================
# KYIV LOCATIONS DICTIONARY
# =============================================================================

KYIV_LOCATIONS = {
    "житомирська": {"aliases": ["житомирка", "житомир тр", "житомирської"], "lat": 50.4401, "lng": 30.3568},
    "хрещатик": {"aliases": ["крещатик"], "lat": 50.4474, "lng": 30.5217},
    "подол": {"aliases": ["поділ"], "lat": 50.4640, "lng": 30.5180},
    "оболонь": {"aliases": ["оболонка"], "lat": 50.5019, "lng": 30.4981},
    "печерськ": {"aliases": ["печерск"], "lat": 50.4308, "lng": 30.5408},
    "дарниця": {"aliases": ["дарница"], "lat": 50.4425, "lng": 30.6291},
    "борщагівка": {"aliases": ["борщаговка"], "lat": 50.4557, "lng": 30.3601},
    "теремки": {"aliases": [], "lat": 50.3850, "lng": 30.4440},
    "академмістечко": {"aliases": ["академгородок"], "lat": 50.4648, "lng": 30.3555},
    "виноградар": {"aliases": [], "lat": 50.5066, "lng": 30.4260},
    "троєщина": {"aliases": ["троещина"], "lat": 50.5200, "lng": 30.6100},
    "позняки": {"aliases": [], "lat": 50.3960, "lng": 30.6180},
    "осокорки": {"aliases": [], "lat": 50.3961, "lng": 30.5848},
    "харківське шосе": {"aliases": ["харьковское шоссе"], "lat": 50.3930, "lng": 30.6550},
    "контрактова площа": {"aliases": ["контрактовая площадь"], "lat": 50.4662, "lng": 30.5172},
    "майдан": {"aliases": ["майдан незалежності"], "lat": 50.4501, "lng": 30.5234},
}

# =============================================================================
# AI SIGNAL CLASSIFIER CLASS
# =============================================================================

class AISignalClassifier:
    """
    AI-powered signal classification service.
    
    Pipeline:
    1. Slang normalization
    2. Negative keyword check
    3. AI classification (GPT-4o-mini)
    4. Location extraction
    5. Multi-location handling
    6. Confidence calculation
    """
    
    def __init__(self, db):
        self.db = db
        self.llm_key = os.environ.get("EMERGENT_LLM_KEY")
        self.llm_available = bool(self.llm_key)
        self.confidence_threshold = float(os.environ.get("AI_CONFIDENCE_THRESHOLD", "0.65"))
        self.model_name = os.environ.get("AI_MODEL", "gpt-4o-mini")
        
        if self.llm_available:
            logger.info(f"AI Classifier initialized with model: {self.model_name}")
        else:
            logger.warning("EMERGENT_LLM_KEY not set, using rule-based classification")
    
    async def classify_message(
        self,
        text: str,
        source_channel: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Full classification pipeline for a message.
        
        Returns:
        {
            "signalType": str,
            "confidence": float,
            "locations": List[Dict],  # Multi-location support
            "severity": str,
            "isNegative": bool,
            "entities": Dict,  # vehicle, color, direction
            "method": str,
            "normalized_text": str
        }
        """
        if not text or len(text.strip()) < 3:
            return {"signalType": None, "confidence": 0, "error": "Text too short"}
        
        # Step 1: Normalize slang
        normalized_text = self._normalize_slang(text)
        
        # Step 2: Check for negative message
        is_negative = self._is_negative(normalized_text)
        
        if is_negative:
            return {
                "signalType": None,
                "confidence": 0,
                "isNegative": True,
                "normalized_text": normalized_text,
                "method": "negative_filter",
                "matched_negatives": self._get_matched_negatives(normalized_text),
            }
        
        # Step 3: AI Classification
        if self.llm_available and len(normalized_text) > 10:
            try:
                result = await self._classify_with_ai(normalized_text, source_channel)
                if result and result.get("signalType"):
                    result["normalized_text"] = normalized_text
                    result["isNegative"] = False
                    return result
            except Exception as e:
                logger.warning(f"AI classification failed: {e}, falling back to rules")
        
        # Step 4: Fallback to rule-based
        result = self._classify_with_rules(normalized_text)
        result["normalized_text"] = normalized_text
        result["isNegative"] = False
        return result
    
    def _normalize_slang(self, text: str) -> str:
        """Normalize slang and abbreviations."""
        text_lower = text.lower()
        
        for slang, normalized in SLANG_DICTIONARY.items():
            # Use word boundaries
            pattern = r'\b' + re.escape(slang) + r'\b'
            text_lower = re.sub(pattern, normalized, text_lower, flags=re.IGNORECASE)
        
        return text_lower
    
    def _is_negative(self, text: str) -> bool:
        """Check if message contains negative keywords."""
        text_lower = text.lower()
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in text_lower:
                return True
        return False
    
    def _get_matched_negatives(self, text: str) -> List[str]:
        """Get list of matched negative keywords."""
        text_lower = text.lower()
        matched = []
        for keyword in NEGATIVE_KEYWORDS:
            if keyword in text_lower:
                matched.append(keyword)
        return matched
    
    async def _classify_with_ai(
        self,
        text: str,
        source_channel: str = None,
    ) -> Dict[str, Any]:
        """
        AI classification using GPT-4o-mini.
        
        Prompt optimized for Ukrainian/Russian Telegram messages.
        """
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            signal_types_str = ", ".join(SIGNAL_TYPES.keys())
            
            system_prompt = f"""You are an AI signal classifier for a Ukrainian crisis-intelligence system.

TASK: Classify the message into one signal type and extract locations.

SIGNAL TYPES:
{signal_types_str}

IMPORTANT:
1. Messages about checkpoints (БП, блокпост, перевіряють) → "checkpoint"
2. Messages about police (поліція, ДПС, патруль) → "police"  
3. Messages about detention/mobilization (ТЦК, забирають, облава) → "detention"
4. Messages about accidents → "accident"
5. If unclear → null

RESPOND ONLY with valid JSON (no markdown):
{{
  "signalType": "checkpoint|police|detention|raid|danger|fire|accident|weather|virus|trash|flood|null",
  "confidence": 0.0-1.0,
  "severity": "low|medium|high|critical",
  "locations": [
    {{"name": "location name", "normalized": "normalized name"}}
  ],
  "entities": {{
    "vehicle": "vehicle type or null",
    "color": "color or null",
    "direction": "direction or null"
  }}
}}
"""
            
            chat = LlmChat(
                api_key=self.llm_key,
                session_id=f"classifier_{hash(text) % 100000}",
                system_message=system_prompt
            ).with_model("openai", self.model_name)
            
            user_message = f"Message from {source_channel or 'user'}:\n{text}"
            response = await chat.send_message(UserMessage(text=user_message))
            
            # Parse JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Try to fix common JSON issues
                    fixed = json_match.group().replace("'", '"')
                    data = json.loads(fixed)
                
                signal_type = data.get("signalType")
                if signal_type == "null" or signal_type not in SIGNAL_TYPES:
                    signal_type = None
                
                # Process locations
                locations = data.get("locations", [])
                processed_locations = []
                for loc in locations:
                    if isinstance(loc, dict) and loc.get("name"):
                        processed_locations.append({
                            "name": loc.get("name"),
                            "normalized": loc.get("normalized", loc.get("name")),
                            "coords": self._get_location_coords(loc.get("name")),
                        })
                
                emoji = SIGNAL_TYPES.get(signal_type, {}).get("emoji", "📍") if signal_type else "📍"
                
                return {
                    "signalType": signal_type,
                    "confidence": float(data.get("confidence", 0.5)),
                    "emoji": emoji,
                    "severity": data.get("severity", "low"),
                    "locations": processed_locations,
                    "entities": data.get("entities", {}),
                    "method": "ai",
                    "model": self.model_name,
                }
            
            logger.warning(f"Could not parse AI response: {response[:200]}")
            return None
            
        except Exception as e:
            logger.error(f"AI classification error: {e}")
            return None
    
    def _classify_with_rules(self, text: str) -> Dict[str, Any]:
        """Rule-based classification using keywords."""
        text_lower = text.lower()
        
        matches = {}
        
        for signal_type, config in SIGNAL_TYPES.items():
            score = 0
            
            for key in ["keywords_ua", "keywords_ru"]:
                for keyword in config.get(key, []):
                    if keyword in text_lower:
                        score += 1
            
            if score > 0:
                matches[signal_type] = score
        
        if not matches:
            return {
                "signalType": None,
                "confidence": 0,
                "emoji": "📍",
                "severity": "low",
                "locations": [],
                "entities": {},
                "method": "rules",
            }
        
        # Get best match
        best_type = max(matches, key=matches.get)
        best_score = matches[best_type]
        
        # Calculate confidence
        confidence = min(1.0, best_score / 4 + 0.4)
        
        # Extract locations
        locations = self._extract_locations(text_lower)
        
        return {
            "signalType": best_type,
            "confidence": round(confidence, 2),
            "emoji": SIGNAL_TYPES[best_type]["emoji"],
            "severity": self._determine_severity(text_lower),
            "locations": locations,
            "entities": {},
            "method": "rules",
        }
    
    def _extract_locations(self, text: str) -> List[Dict]:
        """Extract location mentions from text."""
        text_lower = text.lower()
        locations = []
        
        for location_name, data in KYIV_LOCATIONS.items():
            # Check main name
            if location_name in text_lower:
                locations.append({
                    "name": location_name,
                    "normalized": location_name,
                    "coords": {"lat": data["lat"], "lng": data["lng"]},
                })
                continue
            
            # Check aliases
            for alias in data.get("aliases", []):
                if alias in text_lower:
                    locations.append({
                        "name": alias,
                        "normalized": location_name,
                        "coords": {"lat": data["lat"], "lng": data["lng"]},
                    })
                    break
        
        return locations
    
    def _get_location_coords(self, location_name: str) -> Optional[Dict]:
        """Get coordinates for a location name."""
        if not location_name:
            return None
        
        location_lower = location_name.lower()
        
        for name, data in KYIV_LOCATIONS.items():
            if name in location_lower:
                return {"lat": data["lat"], "lng": data["lng"]}
            
            for alias in data.get("aliases", []):
                if alias in location_lower:
                    return {"lat": data["lat"], "lng": data["lng"]}
        
        return None
    
    def _determine_severity(self, text: str) -> str:
        """Determine severity from text."""
        text_lower = text.lower()
        
        critical_words = ["терміново", "срочно", "екстрено", "критично", "забирають", "хапають"]
        high_words = ["небезпечно", "опасно", "увага", "внимание", "обережно"]
        
        for word in critical_words:
            if word in text_lower:
                return "critical"
        
        for word in high_words:
            if word in text_lower:
                return "high"
        
        return "medium"
    
    async def get_config(self) -> Dict[str, Any]:
        """Get classifier configuration for admin panel."""
        return {
            "llm_available": self.llm_available,
            "model": self.model_name,
            "confidence_threshold": self.confidence_threshold,
            "signal_types": list(SIGNAL_TYPES.keys()),
            "slang_entries": len(SLANG_DICTIONARY),
            "negative_keywords_count": len(NEGATIVE_KEYWORDS),
            "locations_count": len(KYIV_LOCATIONS),
        }
    
    async def update_config(
        self,
        model: str = None,
        confidence_threshold: float = None,
    ) -> Dict[str, Any]:
        """Update classifier configuration."""
        if model:
            self.model_name = model
        if confidence_threshold is not None:
            self.confidence_threshold = confidence_threshold
        
        return await self.get_config()


# =============================================================================
# API ROUTES FOR AI ENGINE
# =============================================================================

async def add_ai_engine_routes(router, db):
    """Add AI Engine admin routes to router."""
    from fastapi import Query, HTTPException
    
    classifier = AISignalClassifier(db)
    
    @router.get("/ai-engine/config")
    async def get_ai_config():
        """Get AI Engine configuration."""
        config = await classifier.get_config()
        return {"ok": True, "config": config}
    
    @router.post("/ai-engine/config")
    async def update_ai_config(
        model: str = Query(None),
        confidence_threshold: float = Query(None, ge=0.0, le=1.0),
    ):
        """Update AI Engine configuration."""
        config = await classifier.update_config(
            model=model,
            confidence_threshold=confidence_threshold,
        )
        return {"ok": True, "config": config}
    
    @router.post("/ai-engine/classify")
    async def classify_text(
        text: str = Query(..., min_length=3),
        source_channel: str = Query(None),
    ):
        """
        Test AI classification on text.
        
        Useful for admin testing.
        """
        result = await classifier.classify_message(text, source_channel)
        return {"ok": True, "result": result}
    
    @router.get("/ai-engine/signal-types")
    async def get_signal_types():
        """Get all signal types with configuration."""
        return {
            "ok": True,
            "types": {
                name: {
                    "emoji": config["emoji"],
                    "priority": config["priority"],
                    "ttl_minutes": config["ttl_minutes"],
                }
                for name, config in SIGNAL_TYPES.items()
            }
        }
    
    @router.get("/ai-engine/locations")
    async def get_locations():
        """Get Kyiv locations dictionary."""
        return {
            "ok": True,
            "locations": {
                name: {
                    "aliases": data["aliases"],
                    "lat": data["lat"],
                    "lng": data["lng"],
                }
                for name, data in KYIV_LOCATIONS.items()
            }
        }
    
    @router.get("/ai-engine/slang")
    async def get_slang_dictionary():
        """Get slang normalization dictionary."""
        return {
            "ok": True,
            "slang": SLANG_DICTIONARY,
            "count": len(SLANG_DICTIONARY),
        }
    
    @router.get("/ai-engine/negative-keywords")
    async def get_negative_keywords():
        """Get negative keywords list."""
        return {
            "ok": True,
            "keywords": NEGATIVE_KEYWORDS,
            "count": len(NEGATIVE_KEYWORDS),
        }
    
    return classifier
