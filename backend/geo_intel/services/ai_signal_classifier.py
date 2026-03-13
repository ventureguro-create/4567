"""
AI Signal Classifier - Text-based signal classification

Uses OpenAI to classify user text messages into signal types:
- virus (🦠) - illness, epidemic, health hazard
- trash (🗑) - garbage, litter, waste
- rain (🌧) - weather, flooding, storm
- police (🚔) - police, checkpoint, accident

Also extracts:
- Location mentions
- Confidence score
- Severity level
"""
import logging
import os
import re
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Signal types
SIGNAL_TYPES = {
    "virus": {
        "emoji": "🦠",
        "keywords_ru": ["вирус", "больн", "заболе", "грипп", "инфекц", "эпидем", "карантин", "ковид", "covid"],
        "keywords_ua": ["вірус", "хвор", "захвор", "грип", "інфекц", "епідем", "карантин", "ковід"],
        "keywords_en": ["virus", "sick", "illness", "flu", "infect", "epidemic", "covid", "disease"]
    },
    "trash": {
        "emoji": "🗑",
        "keywords_ru": ["мусор", "свалк", "грязь", "отход", "помойк", "сметье"],
        "keywords_ua": ["сміття", "звалищ", "бруд", "відход", "помийк"],
        "keywords_en": ["trash", "garbage", "waste", "litter", "dump", "rubbish"]
    },
    "rain": {
        "emoji": "🌧",
        "keywords_ru": ["дождь", "ливень", "потоп", "затопл", "наводн", "гроз", "шторм", "буря"],
        "keywords_ua": ["дощ", "злива", "потоп", "затопл", "повінь", "гроза", "шторм", "буря"],
        "keywords_en": ["rain", "flood", "storm", "thunder", "weather", "downpour"]
    },
    "police": {
        "emoji": "🚔",
        "keywords_ru": ["полиц", "гаи", "дпс", "патруль", "авари", "дтп", "пост", "блокпост"],
        "keywords_ua": ["поліц", "даі", "патруль", "аварі", "дтп", "пост", "блокпост"],
        "keywords_en": ["police", "patrol", "accident", "crash", "checkpoint", "dtp"]
    }
}

# Severity keywords
SEVERITY_HIGH = ["urgent", "срочно", "терміново", "danger", "опасн", "небезпеч", "serious", "серьезн", "серйозн"]
SEVERITY_MEDIUM = ["warning", "внимание", "увага", "caution", "осторожн", "обережн"]


class AISignalClassifier:
    """AI-powered signal classification service"""
    
    def __init__(self, db):
        self.db = db
        self.llm_key = os.environ.get("EMERGENT_LLM_KEY")
        self.llm_available = bool(self.llm_key)
        
        if not self.llm_available:
            logger.warning("EMERGENT_LLM_KEY not set, using rule-based classification")
    
    async def classify_text(self, text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Classify text message into signal type.
        
        Uses AI if available, falls back to rule-based.
        
        Returns:
        {
            "signalType": str,
            "confidence": float (0-1),
            "emoji": str,
            "severity": str (low/medium/high),
            "locationMentioned": str or None,
            "method": str (ai/rules)
        }
        """
        if not text or len(text.strip()) < 3:
            return {"signalType": None, "confidence": 0, "error": "Text too short"}
        
        text_clean = text.strip().lower()
        
        # Try AI classification first
        if self.llm_available and len(text_clean) > 10:
            try:
                result = await self._classify_with_ai(text)
                if result and result.get("signalType"):
                    return result
            except Exception as e:
                logger.warning(f"AI classification failed: {e}, falling back to rules")
        
        # Fallback to rule-based
        return self._classify_with_rules(text_clean)
    
    async def _classify_with_ai(self, text: str) -> Dict[str, Any]:
        """Use OpenAI to classify text"""
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            
            chat = LlmChat(
                api_key=self.llm_key,
                session_id=f"classifier_{hash(text) % 10000}",
                system_message="""You are a signal classifier for a geo-alert system.
Classify the user's message into one of these categories:
- virus: illness, epidemic, health hazard, disease
- trash: garbage, litter, waste, dump
- rain: weather, flooding, storm, rain
- police: police, checkpoint, accident, crash

Respond ONLY with JSON:
{
  "signalType": "virus|trash|rain|police|unknown",
  "confidence": 0.0-1.0,
  "severity": "low|medium|high",
  "locationMentioned": "location name or null"
}
"""
            ).with_model("openai", "gpt-4o-mini")
            
            response = await chat.send_message(UserMessage(text=text))
            
            # Parse JSON from response
            import json
            
            # Try to extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                signal_type = data.get("signalType", "unknown")
                if signal_type not in SIGNAL_TYPES and signal_type != "unknown":
                    signal_type = "unknown"
                
                emoji = SIGNAL_TYPES.get(signal_type, {}).get("emoji", "📍")
                
                return {
                    "signalType": signal_type if signal_type != "unknown" else None,
                    "confidence": float(data.get("confidence", 0.5)),
                    "emoji": emoji,
                    "severity": data.get("severity", "low"),
                    "locationMentioned": data.get("locationMentioned"),
                    "method": "ai"
                }
            
        except Exception as e:
            logger.error(f"AI classification error: {e}")
        
        return None
    
    def _classify_with_rules(self, text: str) -> Dict[str, Any]:
        """Rule-based classification using keywords"""
        text_lower = text.lower()
        
        matches = {}
        
        for signal_type, config in SIGNAL_TYPES.items():
            score = 0
            
            # Check all keyword lists
            for key in ["keywords_ru", "keywords_ua", "keywords_en"]:
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
                "locationMentioned": None,
                "method": "rules"
            }
        
        # Get best match
        best_type = max(matches, key=matches.get)
        best_score = matches[best_type]
        
        # Calculate confidence
        max_possible = 5  # Assume max 5 keywords match
        confidence = min(1.0, best_score / max_possible + 0.3)
        
        # Determine severity
        severity = "low"
        for high_word in SEVERITY_HIGH:
            if high_word in text_lower:
                severity = "high"
                break
        if severity == "low":
            for med_word in SEVERITY_MEDIUM:
                if med_word in text_lower:
                    severity = "medium"
                    break
        
        return {
            "signalType": best_type,
            "confidence": round(confidence, 2),
            "emoji": SIGNAL_TYPES[best_type]["emoji"],
            "severity": severity,
            "locationMentioned": self._extract_location(text),
            "method": "rules"
        }
    
    def _extract_location(self, text: str) -> Optional[str]:
        """Try to extract location mentions from text"""
        # Common location patterns
        patterns = [
            r'(?:біля|возле|near|на|at|в|in)\s+([А-Яа-яІіЇїЄє\w\s]{3,30})',
            r'(?:вулиця|улица|street|вул\.?|ул\.?)\s+([А-Яа-яІіЇїЄє\w\s]{3,30})',
            r'(?:район|area)\s+([А-Яа-яІіЇїЄє\w\s]{3,20})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                location = match.group(1).strip()
                # Clean up
                location = re.sub(r'\s+', ' ', location)
                if len(location) >= 3:
                    return location
        
        return None
    
    async def get_quick_suggestions(self, partial_text: str) -> List[Dict[str, Any]]:
        """Get quick signal type suggestions based on partial text"""
        if not partial_text or len(partial_text) < 2:
            return []
        
        text_lower = partial_text.lower()
        suggestions = []
        
        for signal_type, config in SIGNAL_TYPES.items():
            for key in ["keywords_ru", "keywords_ua", "keywords_en"]:
                for keyword in config.get(key, []):
                    if keyword.startswith(text_lower[:3]) or text_lower[:3] in keyword:
                        suggestions.append({
                            "type": signal_type,
                            "emoji": config["emoji"],
                            "keyword": keyword
                        })
                        break
        
        return suggestions[:3]  # Return top 3
