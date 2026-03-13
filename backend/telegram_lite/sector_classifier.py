"""
Sector Classification Module for Telegram Channels
Classifies channels into sectors: Crypto, DeFi, NFT, Gaming, Trading, News, Education, Community
"""
import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Sector definitions with keywords and patterns
SECTORS = {
    "Crypto": {
        "keywords": [
            "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", 
            "cryptocurrency", "криптовалюта", "крипто", "биткоин", "эфир",
            "altcoin", "альткоин", "coin", "token", "токен"
        ],
        "weight": 1.0,
        "color": "#F7931A",  # Bitcoin orange
    },
    "DeFi": {
        "keywords": [
            "defi", "decentralized finance", "дефи", "yield", "farm", 
            "lending", "swap", "liquidity", "pool", "staking", "stake",
            "apy", "apr", "tvl", "amm", "dex", "uniswap", "aave"
        ],
        "weight": 1.2,
        "color": "#627EEA",  # Ethereum blue
    },
    "NFT": {
        "keywords": [
            "nft", "non-fungible", "opensea", "нфт", "collectible",
            "pfp", "art", "digital art", "mint", "минт", "whitelist",
            "collection", "коллекция", "marketplace"
        ],
        "weight": 1.1,
        "color": "#E6007A",  # Polkadot pink
    },
    "Trading": {
        "keywords": [
            "trading", "трейдинг", "trade", "signal", "сигнал", 
            "analysis", "анализ", "technical", "futures", "фьючерс",
            "leverage", "плечо", "long", "short", "лонг", "шорт",
            "scalp", "скальп", "spot", "margin"
        ],
        "weight": 1.0,
        "color": "#00D395",  # Compound green
    },
    "Gaming": {
        "keywords": [
            "gamefi", "game", "игра", "play to earn", "p2e", "gaming",
            "metaverse", "метавселенная", "axie", "sandbox", "gala"
        ],
        "weight": 1.0,
        "color": "#9945FF",  # Solana purple
    },
    "News": {
        "keywords": [
            "news", "новости", "breaking", "update", "обновлен",
            "announcement", "анонс", "launch", "запуск", "release"
        ],
        "weight": 0.8,
        "color": "#3B82F6",  # Blue
    },
    "Education": {
        "keywords": [
            "education", "образование", "learn", "курс", "course",
            "tutorial", "guide", "гайд", "обучение", "урок", "lesson"
        ],
        "weight": 0.9,
        "color": "#10B981",  # Green
    },
    "Community": {
        "keywords": [
            "community", "сообщество", "chat", "чат", "discussion",
            "обсуждение", "group", "группа", "dao"
        ],
        "weight": 0.7,
        "color": "#8B5CF6",  # Purple
    },
    "Airdrop": {
        "keywords": [
            "airdrop", "эирдроп", "аирдроп", "drop", "free", "giveaway",
            "розыгрыш", "раздача", "bounty", "баунти"
        ],
        "weight": 1.0,
        "color": "#F59E0B",  # Amber
    },
    "ICO": {
        "keywords": [
            "ico", "ido", "ieo", "tokensale", "presale", "пресейл",
            "launchpad", "лаунчпад", "igs"
        ],
        "weight": 1.0,
        "color": "#EF4444",  # Red
    },
}

# Minimum score threshold to assign a sector
MIN_SECTOR_SCORE = 0.15


def normalize_text(text: str) -> str:
    """Normalize text for matching"""
    if not text:
        return ""
    return text.lower().strip()


def classify_channel_sector(
    title: str = "",
    about: str = "",
    posts_text: List[str] = None,
    existing_tags: List[str] = None
) -> Dict:
    """
    Classify channel into sectors based on title, description, and posts.
    
    Returns:
        {
            "primary": "Crypto",  # Main sector
            "secondary": ["DeFi", "Trading"],  # Additional sectors
            "scores": {"Crypto": 0.8, "DeFi": 0.5, ...},
            "confidence": 0.85,
            "tags": ["crypto", "defi", "trading"]
        }
    """
    posts_text = posts_text or []
    existing_tags = existing_tags or []
    
    # Combine all text
    combined_text = normalize_text(f"{title} {about} {' '.join(posts_text[:20])}")
    
    if not combined_text:
        return {
            "primary": "Crypto",  # Default
            "secondary": [],
            "scores": {},
            "confidence": 0.0,
            "tags": []
        }
    
    # Calculate scores for each sector
    sector_scores = {}
    
    for sector, config in SECTORS.items():
        score = 0.0
        matches = []
        
        for keyword in config["keywords"]:
            # Title match has higher weight
            title_matches = len(re.findall(re.escape(keyword), normalize_text(title)))
            if title_matches > 0:
                score += 0.3 * title_matches
                matches.append(keyword)
            
            # About/description matches
            about_matches = len(re.findall(re.escape(keyword), normalize_text(about)))
            if about_matches > 0:
                score += 0.2 * about_matches
                if keyword not in matches:
                    matches.append(keyword)
            
            # Posts text matches
            for post in posts_text[:20]:  # Analyze first 20 posts
                post_matches = len(re.findall(re.escape(keyword), normalize_text(post)))
                if post_matches > 0:
                    score += 0.05 * post_matches
                    if keyword not in matches:
                        matches.append(keyword)
        
        # Apply sector weight
        score *= config["weight"]
        
        # Boost from existing tags
        for tag in existing_tags:
            if tag.lower() in [k.lower() for k in config["keywords"]]:
                score += 0.2
        
        if score > 0:
            sector_scores[sector] = round(score, 3)
    
    # Sort by score
    sorted_sectors = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
    
    # Determine primary and secondary sectors
    primary = None
    secondary = []
    total_score = sum(sector_scores.values()) or 1
    
    if sorted_sectors:
        # Primary sector
        primary = sorted_sectors[0][0] if sorted_sectors[0][1] >= MIN_SECTOR_SCORE else "Crypto"
        
        # Secondary sectors (at least 50% of primary score)
        primary_score = sorted_sectors[0][1]
        for sector, score in sorted_sectors[1:5]:
            if score >= MIN_SECTOR_SCORE and score >= primary_score * 0.4:
                secondary.append(sector)
    else:
        primary = "Crypto"  # Default
    
    # Calculate confidence (0-1)
    if sorted_sectors and total_score > 0:
        top_score = sorted_sectors[0][1]
        confidence = min(1.0, top_score / 2)  # Cap at 1.0, normalize by factor
    else:
        confidence = 0.0
    
    # Generate tags
    tags = [primary.lower()]
    tags.extend([s.lower() for s in secondary[:3]])
    
    return {
        "primary": primary,
        "secondary": secondary[:3],
        "scores": sector_scores,
        "confidence": round(confidence, 2),
        "tags": tags[:5],
        "color": SECTORS.get(primary, {}).get("color", "#6B7280"),
    }


async def classify_and_save_sector(db, username: str) -> Optional[Dict]:
    """
    Classify channel sector and save to database.
    
    Args:
        db: MongoDB database
        username: Channel username
        
    Returns:
        Sector classification result
    """
    # Get channel info
    channel = await db.tg_channel_states.find_one({"username": username})
    if not channel:
        return None
    
    # Get recent posts
    posts = await db.tg_posts.find(
        {"username": username},
        {"text": 1}
    ).sort("date", -1).limit(20).to_list(20)
    
    posts_text = [p.get("text", "") for p in posts if p.get("text")]
    
    # Classify
    result = classify_channel_sector(
        title=channel.get("title", ""),
        about=channel.get("about", ""),
        posts_text=posts_text,
        existing_tags=channel.get("tags", [])
    )
    
    # Save to database
    await db.tg_channel_states.update_one(
        {"username": username},
        {
            "$set": {
                "sector": result["primary"],
                "sectorSecondary": result["secondary"],
                "sectorScores": result["scores"],
                "sectorConfidence": result["confidence"],
                "sectorColor": result["color"],
                "tags": result["tags"],
                "sectorUpdatedAt": __import__("datetime").datetime.utcnow(),
            }
        }
    )
    
    logger.info(f"Classified {username}: {result['primary']} (conf: {result['confidence']})")
    return result


async def batch_classify_sectors(db, limit: int = 100) -> Dict:
    """
    Classify sectors for multiple channels.
    
    Returns:
        {"processed": N, "results": [...]}
    """
    # Get channels without sector classification or outdated
    channels = await db.tg_channel_states.find(
        {
            "$or": [
                {"sector": {"$exists": False}},
                {"sectorUpdatedAt": {"$exists": False}},
            ]
        },
        {"username": 1}
    ).limit(limit).to_list(limit)
    
    results = []
    for ch in channels:
        username = ch.get("username")
        if username:
            result = await classify_and_save_sector(db, username)
            if result:
                results.append({"username": username, "sector": result["primary"]})
    
    return {"processed": len(results), "results": results}


def get_sector_info(sector: str) -> Dict:
    """Get sector metadata"""
    return SECTORS.get(sector, {
        "keywords": [],
        "weight": 1.0,
        "color": "#6B7280"
    })


def list_sectors() -> List[Dict]:
    """List all available sectors"""
    return [
        {
            "name": name,
            "color": config["color"],
            "keywords": len(config["keywords"]),
        }
        for name, config in SECTORS.items()
    ]
