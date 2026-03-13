"""
Signal AI Engine - Main orchestrator for signal intelligence
"""
import logging
import hashlib
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone, timedelta

from .slang import SlangNormalizer, SIGNAL_KEYWORDS
from .classifier import SignalClassifier, SIGNAL_TYPES

logger = logging.getLogger(__name__)

# Kyiv known locations for geocoding fallback
KYIV_LOCATIONS = {
    # Districts
    "дарницький": (50.4108, 30.6285),
    "дарницкий": (50.4108, 30.6285),
    "оболонь": (50.5010, 30.4978),
    "оболонский": (50.5010, 30.4978),
    "подол": (50.4627, 30.5146),
    "поділ": (50.4627, 30.5146),
    "печерськ": (50.4284, 30.5410),
    "печерск": (50.4284, 30.5410),
    "святошин": (50.4589, 30.3657),
    "святошино": (50.4589, 30.3657),
    "шевченківський": (50.4545, 30.4823),
    "шевченковский": (50.4545, 30.4823),
    "голосіївський": (50.3897, 30.5137),
    "голосеевский": (50.3897, 30.5137),
    "солом'янка": (50.4325, 30.4453),
    "соломенка": (50.4325, 30.4453),
    "деснянський": (50.5166, 30.6084),
    "деснянский": (50.5166, 30.6084),
    
    # Metro stations
    "академгородок": (50.3643, 30.4616),
    "академмістечко": (50.3643, 30.4616),
    "вокзальна": (50.4418, 30.4891),
    "вокзальная": (50.4418, 30.4891),
    "хрещатик": (50.4472, 30.5219),
    "крещатик": (50.4472, 30.5219),
    "майдан": (50.4501, 30.5234),
    "лівобережна": (50.5136, 30.6007),
    "левобережная": (50.5136, 30.6007),
    "дарниця": (50.4554, 30.6127),
    "дарница": (50.4554, 30.6127),
    "позняки": (50.3976, 30.6336),
    "осокорки": (50.4014, 30.6123),
    "харківська": (50.4007, 30.6192),
    "харьковская": (50.4007, 30.6192),
    "видубичі": (50.4101, 30.5645),
    "выдубичи": (50.4101, 30.5645),
    "славутич": (50.3939, 30.6038),
    "теремки": (50.3601, 30.4733),
    "либідська": (50.4207, 30.5228),
    "лыбедская": (50.4207, 30.5228),
    "палац спорту": (50.4378, 30.5212),
    "дворец спорта": (50.4378, 30.5212),
    "площа льва толстого": (50.4390, 30.5167),
    "площадь толстого": (50.4390, 30.5167),
    
    # Popular places
    "кульженка": (50.4989, 30.4756),
    "виговського": (50.4650, 30.3889),
    "выговского": (50.4650, 30.3889),
    "героїв дніпра": (50.5227, 30.4988),
    "героев днепра": (50.5227, 30.4988),
    "петрівка": (50.4798, 30.4698),
    "петровка": (50.4798, 30.4698),
    "борщагівка": (50.4567, 30.3567),
    "борщаговка": (50.4567, 30.3567),
    "троєщина": (50.5342, 30.6123),
    "троещина": (50.5342, 30.6123),
    "березняки": (50.4298, 30.5876),
    "русанівка": (50.4445, 30.5756),
    "русановка": (50.4445, 30.5756),
    
    # Roads
    "житомирська траса": (50.4567, 30.3123),
    "житомирская трасса": (50.4567, 30.3123),
    "броварський проспект": (50.4456, 30.5789),
    "броварской проспект": (50.4456, 30.5789),
    "перемоги проспект": (50.4567, 30.4234),
    "проспект победы": (50.4567, 30.4234),
    "бандери": (50.4634, 30.4123),
    "бандеры": (50.4634, 30.4123),
    
    # Bridges
    "дарницький міст": (50.4389, 30.5612),
    "дарницкий мост": (50.4389, 30.5612),
    "південний міст": (50.3934, 30.5523),
    "южный мост": (50.3934, 30.5523),
    "північний міст": (50.5023, 30.5567),
    "северный мост": (50.5023, 30.5567),
    "міст патона": (50.4345, 30.5567),
    "мост патона": (50.4345, 30.5567),
}


class SignalAIEngine:
    """
    Main Signal Intelligence Engine
    Processes Telegram posts and extracts structured signals
    """
    
    def __init__(self, db=None):
        self.db = db
        self.normalizer = SlangNormalizer()
        self.classifier = SignalClassifier(db)
        self.confidence_threshold = 0.6
        self.dedup_radius_km = 0.2  # 200 meters
        self.ai_enabled = False
    
    async def initialize(self):
        """Initialize engine with database settings"""
        await self.classifier.initialize()
        
        if self.db:
            try:
                # Load custom slang from DB
                async for doc in self.db.slang_dictionary.find():
                    self.normalizer.add_slang(doc["word"], doc["meaning"])
                
                # Load settings
                settings = await self.db.system_settings.find_one({"key": "ai_settings"})
                if settings and settings.get("value"):
                    self.confidence_threshold = settings["value"].get("confidence_threshold", 0.6)
                    self.ai_enabled = settings["value"].get("enabled", False)
                    
            except Exception as e:
                logger.error(f"Failed to load engine settings: {e}")
    
    def split_post(self, post_text: str) -> List[str]:
        """Split post into individual message lines"""
        if not post_text:
            return []
        
        # Split by newlines and clean
        lines = post_text.split("\n")
        cleaned = []
        
        for line in lines:
            line = line.strip()
            # Skip empty lines and very short lines
            if len(line) < 5:
                continue
            # Skip lines that are just emojis or timestamps
            if re.match(r'^[\d:,\.\s]+$', line):
                continue
            if re.match(r'^[^\w\s]+$', line):
                continue
            cleaned.append(line)
        
        return cleaned
    
    def extract_location(self, text: str) -> Optional[Tuple[str, float, float]]:
        """
        Extract location from text and return (name, lat, lng)
        Uses local dictionary first, then could call external geocoder
        """
        text_lower = text.lower()
        
        # Check known locations
        for location, coords in KYIV_LOCATIONS.items():
            if location in text_lower:
                return (location, coords[0], coords[1])
        
        # Try to extract location patterns
        patterns = [
            r'(?:на|біля|в районі|район[іе]?)\s+([а-яіїєґА-ЯІЇЄҐ][а-яіїєґА-ЯІЇЄҐ\s]{2,25})',
            r'(?:вул(?:иця|\.)?|вулиці)\s+([а-яіїєґА-ЯІЇЄҐ][а-яіїєґА-ЯІЇЄҐ\s]{2,25})',
            r'(?:пр(?:оспект|\.)?)\s+([а-яіїєґА-ЯІЇЄҐ][а-яіїєґА-ЯІЇЄҐ\s]{2,25})',
            r'(?:м(?:етро|\.)?)\s+([а-яіїєґА-ЯІЇЄҐ][а-яіїєґА-ЯІЇЄҐ\s]{2,25})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                location_name = match.group(1).strip()
                # Check if this extracted name is in our dictionary
                if location_name in KYIV_LOCATIONS:
                    coords = KYIV_LOCATIONS[location_name]
                    return (location_name, coords[0], coords[1])
                # Return name without coords for later geocoding
                return (location_name, None, None)
        
        return None
    
    async def process_line(self, line: str, channel_username: str = None) -> Optional[Dict[str, Any]]:
        """
        Process single line and extract signal
        Returns signal dict or None if not a valid signal
        """
        # Step 1: Check for negative keywords
        if self.normalizer.has_negative_keywords(line):
            return None
        
        # Step 2: Quick keyword classification
        quick_type, quick_confidence = self.normalizer.quick_classify(line)
        
        # Step 3: Normalize text
        normalized = self.normalizer.normalize(line)
        
        # Step 4: Extract location
        location_data = self.extract_location(line)
        
        # Step 5: Decide if we need AI
        use_ai = False
        if self.ai_enabled and self.classifier.openai_client:
            # Use AI if:
            # - Quick classification failed or low confidence
            # - Has keywords but ambiguous
            if quick_type is None or quick_confidence < 0.7:
                use_ai = True
        
        # Step 6: Classify
        if use_ai:
            result = await self.classifier.classify(normalized)
        else:
            # Use quick classification
            if quick_type and quick_confidence >= self.confidence_threshold:
                result = {
                    "type": quick_type,
                    "confidence": quick_confidence,
                    "description": f"Detected via keywords",
                    "ai_used": False
                }
            else:
                # If no AI and no quick match, skip
                return None
        
        # Step 7: Filter by confidence
        if result.get("confidence", 0) < self.confidence_threshold:
            return None
        
        # Step 8: Build signal
        signal = {
            "type": result["type"],
            "confidence": result["confidence"],
            "description": result.get("description", ""),
            "originalText": line,
            "normalizedText": normalized,
            "aiUsed": result.get("ai_used", False),
            "source": channel_username,
            "createdAt": datetime.now(timezone.utc),
        }
        
        # Add location if found
        if location_data:
            signal["locationName"] = location_data[0]
            if location_data[1] and location_data[2]:
                signal["lat"] = location_data[1]
                signal["lng"] = location_data[2]
        elif result.get("location"):
            signal["locationName"] = result["location"]
            # Try to geocode AI-extracted location
            ai_location = self.extract_location(result["location"])
            if ai_location and ai_location[1]:
                signal["lat"] = ai_location[1]
                signal["lng"] = ai_location[2]
        
        # Add TTL
        signal_config = SIGNAL_TYPES.get(signal["type"], SIGNAL_TYPES["trash"])
        ttl_minutes = signal_config["ttl"]
        signal["expiresAt"] = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        
        return signal
    
    async def process_post(self, post_text: str, channel_username: str = None) -> List[Dict[str, Any]]:
        """
        Process entire post and extract all signals
        Returns list of signals
        """
        signals = []
        lines = self.split_post(post_text)
        
        for line in lines:
            try:
                signal = await self.process_line(line, channel_username)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error processing line '{line[:50]}...': {e}")
        
        return signals
    
    async def is_duplicate(self, signal: Dict, radius_km: float = None) -> bool:
        """
        Check if signal is duplicate of existing one
        Uses location proximity and time window
        """
        if not self.db or not signal.get("lat"):
            return False
        
        radius = radius_km or self.dedup_radius_km
        
        # Check for similar signals in last hour
        time_window = datetime.now(timezone.utc) - timedelta(hours=1)
        
        try:
            # Find nearby signals of same type
            existing = await self.db.geo_signals.find_one({
                "type": signal["type"],
                "createdAt": {"$gte": time_window},
                "lat": {"$gte": signal["lat"] - 0.002, "$lte": signal["lat"] + 0.002},
                "lng": {"$gte": signal["lng"] - 0.002, "$lte": signal["lng"] + 0.002}
            })
            
            return existing is not None
            
        except Exception as e:
            logger.error(f"Duplicate check error: {e}")
            return False
    
    async def save_signal(self, signal: Dict) -> Optional[str]:
        """
        Save signal to database after deduplication
        Returns signal ID if saved, None if duplicate
        """
        if self.db is None:
            return None
        
        # Check for duplicate
        if await self.is_duplicate(signal):
            logger.info(f"Duplicate signal detected: {signal['type']} at {signal.get('locationName')}")
            return None
        
        try:
            result = await self.db.geo_signals.insert_one(signal)
            logger.info(f"Signal saved: {signal['type']} at {signal.get('locationName')} (confidence: {signal['confidence']:.2f})")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
            return None
    
    async def process_and_save_post(self, post_text: str, channel_username: str = None) -> Dict[str, Any]:
        """
        Full pipeline: process post, deduplicate, and save signals
        Returns summary of processing
        """
        signals = await self.process_post(post_text, channel_username)
        
        saved_count = 0
        duplicate_count = 0
        
        for signal in signals:
            signal_id = await self.save_signal(signal)
            if signal_id:
                saved_count += 1
            else:
                duplicate_count += 1
        
        return {
            "processed": len(signals),
            "saved": saved_count,
            "duplicates": duplicate_count,
            "signals": signals
        }
    
    async def get_active_signals(self, hours: int = 2) -> List[Dict]:
        """Get active (non-expired) signals"""
        if self.db is None:
            return []
        
        now = datetime.now(timezone.utc)
        
        try:
            cursor = self.db.geo_signals.find(
                {"expiresAt": {"$gt": now}},
                {"_id": 0}
            ).sort("createdAt", -1).limit(100)
            
            return await cursor.to_list(length=100)
        except Exception as e:
            logger.error(f"Failed to get active signals: {e}")
            return []
    
    async def cleanup_expired(self) -> int:
        """Remove expired signals"""
        if self.db is None:
            return 0
        
        now = datetime.now(timezone.utc)
        
        try:
            result = await self.db.geo_signals.delete_many({"expiresAt": {"$lt": now}})
            return result.deleted_count
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return 0
