"""
Event Types Configuration
Defines all supported geo event types with their properties
"""

EVENT_TYPES = {
    "virus": {
        "icon": "🦠",
        "color": "#2ecc71",
        "severity": 3,
        "lifetime_minutes": 60,
        "avoidance_radius": 80,
        "label_uk": "вірус",
        "label_en": "virus"
    },
    "trash": {
        "icon": "🗑️",
        "color": "#3498db",
        "severity": 2,
        "lifetime_minutes": 120,
        "avoidance_radius": 40,
        "label_uk": "сміття",
        "label_en": "trash"
    },
    "rain": {
        "icon": "🌧️",
        "color": "#5dade2",
        "severity": 1,
        "lifetime_minutes": 45,
        "avoidance_radius": 20,
        "label_uk": "дощ",
        "label_en": "rain"
    },
    "heavy_rain": {
        "icon": "⛈️",
        "color": "#2e86c1",
        "severity": 4,
        "lifetime_minutes": 90,
        "avoidance_radius": 60,
        "label_uk": "сильний дощ",
        "label_en": "heavy rain"
    }
}

# Default event type for unknown
DEFAULT_EVENT_TYPE = "virus"


def get_event_config(event_type: str) -> dict:
    """Get configuration for event type"""
    return EVENT_TYPES.get(event_type, EVENT_TYPES[DEFAULT_EVENT_TYPE])


def get_lifetime(event_type: str) -> int:
    """Get lifetime in minutes for event type"""
    return get_event_config(event_type).get("lifetime_minutes", 60)


def get_severity(event_type: str) -> int:
    """Get severity level for event type"""
    return get_event_config(event_type).get("severity", 2)


def get_avoidance_radius(event_type: str) -> int:
    """Get avoidance radius in meters for route planning"""
    return get_event_config(event_type).get("avoidance_radius", 50)


# Trigger words for event classification (Ukrainian)
TRIGGER_WORDS = {
    "virus": [
        "бачив", "бачила", "помітив", "помітила", 
        "знаходяться", "помічено", "спостерігали",
        "зафіксовано", "виявлено"
    ],
    "trash": [
        "сміття", "залишилось", "сліди", "забруднення",
        "відходи", "непотріб"
    ],
    "rain": [
        "дощ", "дощик", "крапає", "мокро"
    ],
    "heavy_rain": [
        "злива", "ливень", "потоп", "сильний дощ",
        "грім", "гроза"
    ]
}


def classify_event_by_text(text: str) -> str:
    """
    Classify event type based on text content.
    Returns event type or 'unknown'.
    """
    text_lower = text.lower()
    
    # Check heavy_rain first (more specific)
    for word in TRIGGER_WORDS.get("heavy_rain", []):
        if word in text_lower:
            return "heavy_rain"
    
    # Then rain
    for word in TRIGGER_WORDS.get("rain", []):
        if word in text_lower:
            return "rain"
    
    # Then trash
    for word in TRIGGER_WORDS.get("trash", []):
        if word in text_lower:
            return "trash"
    
    # Default to virus for observation-like messages
    for word in TRIGGER_WORDS.get("virus", []):
        if word in text_lower:
            return "virus"
    
    return "unknown"
