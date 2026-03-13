"""
Geo Intel Dev Seed - Realistic test data for map visualization
Creates gradient density distribution across Kyiv
"""
import random
import hashlib
from datetime import datetime, timezone, timedelta

# Kyiv districts with coordinates
DISTRICTS = {
    "center": {
        "name": "Центр (Крещатик)",
        "lat": 50.4501,
        "lng": 30.5234,
        "radius": 0.015,  # ~1.5km spread
        "weight": 0.45,   # 45% of points
    },
    "podil": {
        "name": "Подол",
        "lat": 50.4680,
        "lng": 30.5150,
        "radius": 0.012,
        "weight": 0.20,   # 20%
    },
    "pechersk": {
        "name": "Печерск",
        "lat": 50.4260,
        "lng": 30.5400,
        "radius": 0.010,
        "weight": 0.15,   # 15%
    },
    "obolon": {
        "name": "Оболонь",
        "lat": 50.5050,
        "lng": 30.4980,
        "radius": 0.018,
        "weight": 0.10,   # 10%
    },
    "darnytsia": {
        "name": "Дарниця",
        "lat": 50.4310,
        "lng": 30.6230,
        "radius": 0.015,
        "weight": 0.10,   # 10%
    },
}

# Place names for realistic data
PLACES = {
    "center": [
        "Крещатик 12", "Майдан Незалежності", "ТЦ Глобус", "Пасаж",
        "Бессарабська площа", "Хрещатик 22", "Київська мерія",
        "Будинок профспілок", "ЦУМ Київ", "Готель Україна",
    ],
    "podil": [
        "Контрактова площа", "Поштова площа", "Річковий вокзал",
        "Гостинний двір", "Андріївський узвіз", "Флорівський монастир",
        "Подільський ринок", "Набережно-Хрещатицька", "Сагайдачного 25",
    ],
    "pechersk": [
        "Києво-Печерська Лавра", "Арсенальна", "Парк Слави",
        "Національний музей", "Меморіал ВВВ", "Печерський район",
        "Кловський узвіз", "Інститутська", "Липки",
    ],
    "obolon": [
        "Оболонська набережна", "Мінська площа", "ТРЦ Dreamtown",
        "Оболонь Резиденс", "Героїв Дніпра", "Північний міст",
        "Оболонський проспект", "Озеро Оболонь",
    ],
    "darnytsia": [
        "Дарницька площа", "ТРЦ Дарниця", "Позняки",
        "Харківська площа", "Вокзальна Дарниця", "Осокорки",
        "Лівобережна", "Комсомольський масив",
    ],
}

EVENT_TYPES = [
    ("virus", 0.4),
    ("trash", 0.3),
    ("rain", 0.2),
    ("heavy_rain", 0.1),
]

CHANNELS = [
    "kyiv_now", "kyiv_life", "kyiv_info", "kyiv_news_ua",
    "podil_kyiv", "pechersk_news", "obolon_ua", "darnytsia_info",
]


def random_in_radius(lat, lng, radius):
    """Generate random point within radius of center"""
    # Random angle and distance
    angle = random.uniform(0, 2 * 3.14159)
    r = radius * (random.random() ** 0.5)  # Square root for uniform distribution
    
    new_lat = lat + r * 0.9 * (random.random() - 0.5) * 2
    new_lng = lng + r * 1.5 * (random.random() - 0.5) * 2
    
    return new_lat, new_lng


def select_district():
    """Select district based on weight distribution"""
    r = random.random()
    cumulative = 0
    for key, district in DISTRICTS.items():
        cumulative += district["weight"]
        if r <= cumulative:
            return key
    return "center"


def select_event_type():
    """Select event type based on weight distribution"""
    r = random.random()
    cumulative = 0
    for event_type, weight in EVENT_TYPES:
        cumulative += weight
        if r <= cumulative:
            return event_type
    return "place"


async def seed_geo_events(db, count=200):
    """
    Seed geo events with gradient density distribution.
    Creates realistic test data for map visualization.
    """
    now = datetime.now(timezone.utc)
    inserted = 0
    
    # Clear existing test data
    await db.tg_geo_events.delete_many({"source.username": {"$regex": "^(kyiv_|podil_|pechersk_|obolon_|darnytsia_|test_)"}})
    
    for i in range(count):
        # Select district and place
        district_key = select_district()
        district = DISTRICTS[district_key]
        
        # Random position within district
        lat, lng = random_in_radius(
            district["lat"],
            district["lng"],
            district["radius"]
        )
        
        # Select place name
        place_names = PLACES.get(district_key, PLACES["center"])
        place_name = random.choice(place_names)
        
        # Select event type
        event_type = select_event_type()
        
        # Random time - 30% in last hour (for fusion), 70% in last 7 days
        if random.random() < 0.3:
            # Fresh events for fusion testing
            minutes_ago = random.randint(0, 60)
            event_time = now - timedelta(minutes=minutes_ago)
        else:
            # Historical events
            hours_ago = random.randint(1, 168)  # 7 days
            event_time = now - timedelta(hours=hours_ago)
        
        # Random channel
        channel = random.choice(CHANNELS)
        message_id = random.randint(10000, 99999)
        
        # Generate dedupe key
        dedupe_key = hashlib.sha256(
            f"seed:{i}:{district_key}:{place_name}".encode()
        ).hexdigest()[:24]
        
        doc = {
            "actorId": "anon",
            "dedupeKey": dedupe_key,
            "source": {
                "username": channel,
                "messageId": message_id,
                "date": event_time,
            },
            "eventType": event_type,
            "title": place_name,
            "addressText": f"{place_name}, Київ",
            "location": {"lat": lat, "lng": lng},
            "geoPrecision": random.choice(["exact", "approx", "approx"]),
            "evidenceText": f"Тестове повідомлення про {place_name}. Район: {district['name']}.",
            "entities": [],
            "tags": [district_key, event_type],
            "metrics": {
                "views": random.randint(500, 15000),
                "forwards": random.randint(10, 500),
                "replies": random.randint(5, 100),
            },
            "score": random.uniform(0.3, 0.95),
            "createdAt": event_time,
            "updatedAt": now,
        }
        
        try:
            await db.tg_geo_events.insert_one(doc)
            inserted += 1
        except Exception as e:
            print(f"Insert error: {e}")
    
    print(f"Seeded {inserted} geo events across {len(DISTRICTS)} districts")
    return {"inserted": inserted, "districts": list(DISTRICTS.keys())}


async def clear_seed_data(db):
    """Remove all seeded test data"""
    result = await db.tg_geo_events.delete_many({
        "source.username": {"$regex": "^(kyiv_|podil_|pechersk_|obolon_|darnytsia_|test_)"}
    })
    return {"deleted": result.deleted_count}
