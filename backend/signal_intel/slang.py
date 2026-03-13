"""
Slang Normalizer - converts Telegram slang to normalized text
"""
import re
from typing import Dict, List, Tuple

# Default slang dictionary - Ukrainian/Russian Telegram slang
DEFAULT_SLANG_MAP = {
    # Police slang
    "баклажан": "police",
    "баклажаны": "police", 
    "баклажани": "police",
    "сині": "police",
    "синие": "police",
    "синій": "police",
    "мент": "police",
    "менты": "police",
    "менти": "police",
    "мусора": "police",
    "мусарки": "police",
    "мусорки": "police",
    "полиция": "police",
    "поліція": "police",
    "синєва": "police",
    "копы": "police",
    "копи": "police",
    
    # Military/TCK slang
    "зелені": "military TCK",
    "зеленые": "military TCK",
    "зелений": "military TCK",
    "гуси": "military patrol TCK",
    "тцк": "military recruitment TCK",
    "тцкшники": "military recruitment officers",
    "воєнкомат": "military recruitment office",
    "военкомат": "military recruitment office",
    "хлопчики": "military patrol",
    "бусики": "military patrol van",
    "бусик": "military patrol van",
    
    # Detention actions
    "пакують": "detaining people",
    "пакують хлопців": "detaining young men",
    "забрали": "detained taken away",
    "зупинили": "stopped detained",
    "тормозят": "stopping detaining",
    "тормознули": "stopped detained",
    "ловлять": "catching people",
    "ловят": "catching people",
    "повезли": "took away detained",
    "затащили": "dragged detained",
    "затягнули": "dragged detained",
    "закинули": "threw into van detained",
    "виловлюють": "catching hunting people",
    "вилавливают": "catching hunting people",
    
    # Checkpoint
    "бп": "checkpoint blockpost",
    "блокпост": "checkpoint blockpost",
    "блок пост": "checkpoint blockpost",
    "мини бп": "small checkpoint",
    "міні бп": "small checkpoint",
    "кп": "checkpoint",
    "пост": "checkpoint post",
    
    # Raid/Search
    "облава": "raid search operation",
    "рейд": "raid search operation",
    "шмон": "search raid",
    "обшук": "search raid",
    "выскакивают": "jumping out raiding",
    "вискакують": "jumping out raiding",
    "пасутся": "patrolling searching",
    "пасуться": "patrolling searching",
    "видивляються": "watching searching",
    "высматривают": "watching searching looking",
    "шукають": "searching looking for",
    "ищут": "searching looking for",
    "чекають": "waiting ambush",
    "ждут": "waiting ambush",
    "стоять": "standing stationed",
    "стоят": "standing stationed",
    "катаються": "driving around patrolling",
    "катаются": "driving around patrolling",
    "їздять": "driving around patrolling",
    "ездят": "driving around patrolling",
    
    # Weather
    "гроза": "thunderstorm weather",
    "злива": "heavy rain weather",
    "ливень": "heavy rain weather",
    "дождь": "rain weather",
    "дощ": "rain weather",
    "град": "hail weather",
    "шторм": "storm weather",
    "вітер": "wind weather",
    "ветер": "wind weather",
    
    # Safe indicators (negative signals)
    "вільно": "clear safe no danger",
    "чисто": "clear safe no danger",
    "свободно": "clear safe no danger",
    "нема нікого": "nobody no danger",
    "никого нет": "nobody no danger",
    "поехали": "left gone",
    "поїхали": "left gone",
    "уехали": "left gone",
    
    # Vehicles
    "бус": "van",
    "бусик": "small van",
    "спринтер": "sprinter van",
    "газель": "gazelle van",
    "буханка": "UAZ van",
}

# Keywords that indicate signal types
SIGNAL_KEYWORDS = {
    "police": [
        "сині", "синие", "поліція", "полиция", "мент", "менты", "баклажан",
        "копы", "копи", "мусора", "патруль"
    ],
    "detention": [
        "забрали", "зупинили", "пакують", "повезли", "затащили", "затягнули",
        "тормозят", "закинули", "ловлять", "ловят"
    ],
    "checkpoint": [
        "бп", "блокпост", "кп", "пост", "перевірка", "проверка"
    ],
    "raid": [
        "облава", "рейд", "шмон", "выскакивают", "вискакують", "пасутся",
        "пасуться", "видивляються", "шукають", "ищут"
    ],
    "weather": [
        "гроза", "злива", "ливень", "дождь", "дощ", "град", "шторм"
    ],
    "tck": [
        "тцк", "зелені", "зеленые", "гуси", "воєнкомат", "военкомат",
        "бусик", "хлопчики"
    ]
}

# Negative keywords - if present, likely not a signal
NEGATIVE_KEYWORDS = [
    "вільно", "чисто", "свободно", "нема нікого", "никого нет",
    "поехали", "поїхали", "уехали", "все ок", "все добре"
]


class SlangNormalizer:
    """Normalizes Telegram slang to standard text for AI processing"""
    
    def __init__(self, custom_slang: Dict[str, str] = None):
        self.slang_map = {**DEFAULT_SLANG_MAP}
        if custom_slang:
            self.slang_map.update(custom_slang)
    
    def normalize(self, text: str) -> str:
        """Replace slang words with normalized versions"""
        normalized = text.lower()
        
        # Sort by length descending to replace longer phrases first
        sorted_slang = sorted(self.slang_map.items(), key=lambda x: len(x[0]), reverse=True)
        
        for slang, normal in sorted_slang:
            # Use word boundary matching where possible
            pattern = re.compile(re.escape(slang), re.IGNORECASE)
            normalized = pattern.sub(normal, normalized)
        
        return normalized
    
    def detect_keywords(self, text: str) -> Dict[str, List[str]]:
        """Detect signal keywords in text"""
        text_lower = text.lower()
        found = {}
        
        for signal_type, keywords in SIGNAL_KEYWORDS.items():
            matches = [kw for kw in keywords if kw in text_lower]
            if matches:
                found[signal_type] = matches
        
        return found
    
    def has_signal_keywords(self, text: str) -> bool:
        """Check if text contains any signal keywords"""
        return len(self.detect_keywords(text)) > 0
    
    def has_negative_keywords(self, text: str) -> bool:
        """Check if text contains negative/safe keywords"""
        text_lower = text.lower()
        return any(neg in text_lower for neg in NEGATIVE_KEYWORDS)
    
    def quick_classify(self, text: str) -> Tuple[str, float]:
        """
        Quick classification without AI based on keywords
        Returns (type, confidence) or (None, 0) if unsure
        """
        if self.has_negative_keywords(text):
            return ("safe", 0.8)
        
        keywords = self.detect_keywords(text)
        
        if not keywords:
            return (None, 0.0)
        
        # Priority order for classification
        priority = ["detention", "checkpoint", "raid", "tck", "police", "weather"]
        
        for signal_type in priority:
            if signal_type in keywords:
                # More keywords = higher confidence
                confidence = min(0.5 + len(keywords[signal_type]) * 0.15, 0.85)
                return (signal_type, confidence)
        
        return (None, 0.0)
    
    def add_slang(self, word: str, meaning: str):
        """Add new slang word to dictionary"""
        self.slang_map[word.lower()] = meaning
    
    def get_slang_dict(self) -> Dict[str, str]:
        """Get current slang dictionary"""
        return self.slang_map.copy()
