"""
Geo Intel Place/Event Extractor
Extracts places, addresses, venues from Telegram post text
"""
import re
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Patterns for place extraction (Ukrainian, Russian, English)
PLACE_PATTERNS = [
    # Ukrainian addresses
    r"(?:вул\.|вулиця|просп\.|проспект|бульв\.|бульвар|пл\.|площа|пров\.|провулок)\s*([А-ЯІЇЄа-яіїє\w\-\.\s]{2,60})\s*(\d{1,4}[а-яА-Я]?)?",
    # Russian addresses  
    r"(?:ул\.|улица|просп\.|проспект|бульвар|пл\.|площа)\s*([А-Яа-яЁё\w\-\.\s]{2,60})\s*(\d{1,4}[а-яА-Я]?)?",
    # Named places (restaurants, cafes, etc)
    r"(?:в|на|у|біля|возле)\s+(?:ресторан[іие]?|кафе|бар[іие]?|клуб[іие]?|ТРЦ|ТЦ|БЦ)\s+[«\"]?([А-ЯІЇЄа-яіїєA-Za-z\w\-\.\s]{2,50})[»\"]?",
    # Districts/neighborhoods
    r"(?:район[іие]?|на|в)\s+(Подол[іие]?|Печерськ[уа]?|Оболон[ьі]|Троєщин[аі]|Позняк[иах]|Дарниц[яі]|Теремк[иах]|Борщагівк[аі]|Святошин[оа]|Виноград[ар]|Харків[ськаі]+|Дніпр[оа]|Одес[аі]|Льві[ва])",
    # Metro stations
    r"(?:метро|м\.)\s*[«\"]?([А-ЯІЇЄа-яіїє\w\-\s]{3,40})[»\"]?",
    # Specific venues
    r"(?:ЖК|жк|житловий комплекс)\s+[«\"]?([А-ЯІЇЄа-яіїєA-Za-z\w\-\.\s]{2,50})[»\"]?",
]

# Deny list - dangerous/sensitive keywords to filter out
DENY_KEYWORDS = [
    # Military/security (UA)
    "блокпост", "патруль", "військов", "поліці", "сбу", "перевірк", "рейд", "засад",
    "зрк", "ппо", "бпла", "дрон", "ракет", "снаряд", "обстріл", "вибух", "сирен",
    # Military/security (RU)
    "блокпост", "патруль", "военн", "полиц", "фсб", "проверк", "рейд", "засад",
    "зрк", "пво", "бпла", "дрон", "ракет", "снаряд", "обстрел", "взрыв", "сирен",
    # Generic dangerous
    "checkpoint", "military", "police", "raid", "patrol", "missile", "drone", "explosion"
]

# Event type classification keywords
EVENT_TYPE_KEYWORDS = {
    "food": ["ресторан", "кафе", "бар", "піцер", "суші", "бургер", "їдальн", "кав'ярн", "кофейн"],
    "venue": ["клуб", "театр", "кіно", "музей", "галере", "стадіон", "арена", "парк"],
    "traffic": ["затор", "пробк", "перекрит", "ремонт дороги", "дтп", "аварі"],
    "weather": ["дощ", "сніг", "гроза", "туман", "мороз", "спека", "погода"],
    "infrastructure": ["світло", "вода", "газ", "відключен", "ремонт", "аварій"],
    "public_event": ["мітинг", "концерт", "фестиваль", "виставка", "ярмарок", "акці"],
}


def contains_denied(text: str) -> bool:
    """Check if text contains denied/sensitive keywords"""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in DENY_KEYWORDS)


def classify_event_type(text: str) -> str:
    """Classify event type based on keywords"""
    if not text:
        return "other"
    t = text.lower()
    
    for event_type, keywords in EVENT_TYPE_KEYWORDS.items():
        if any(k in t for k in keywords):
            return event_type
    
    return "place"  # Default to generic place


def extract_places(text: str) -> List[Dict]:
    """
    Extract place candidates from text.
    Returns list of {title, addressText, eventType} dicts.
    """
    if not text or len(text) < 10:
        return []
    
    # Skip if contains dangerous content
    if contains_denied(text):
        logger.debug(f"Skipping text with denied keywords")
        return []
    
    candidates = []
    seen_titles = set()
    
    for pattern in PLACE_PATTERNS:
        try:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.UNICODE):
                groups = [g for g in match.groups() if g]
                if not groups:
                    continue
                
                title = " ".join(groups).strip()
                # Clean up
                title = re.sub(r'\s+', ' ', title)
                title = title.strip('.,;:!?«»"\'')
                
                if len(title) < 3 or len(title) > 100:
                    continue
                
                # Skip if already seen (case-insensitive)
                title_lower = title.lower()
                if title_lower in seen_titles:
                    continue
                seen_titles.add(title_lower)
                
                event_type = classify_event_type(text)
                
                candidates.append({
                    "title": title,
                    "addressText": title,
                    "eventType": event_type,
                    "matchedPattern": pattern[:50],
                })
                
        except Exception as e:
            logger.warning(f"Pattern match error: {e}")
            continue
    
    # Limit to 10 candidates per text
    return candidates[:10]


def extract_entities(text: str) -> List[Dict]:
    """Extract named entities (simpler version without NER)"""
    entities = []
    
    # Extract hashtags as tags
    hashtags = re.findall(r'#([А-Яа-яІіЇїЄєA-Za-z0-9_]+)', text)
    for tag in hashtags[:5]:
        entities.append({"kind": "tag", "value": tag.lower()})
    
    # Extract @mentions as potential channels
    mentions = re.findall(r'@([A-Za-z0-9_]{4,32})', text)
    for mention in mentions[:3]:
        entities.append({"kind": "channel", "value": mention.lower()})
    
    return entities
