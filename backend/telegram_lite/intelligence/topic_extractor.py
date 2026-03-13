"""
Topic Extraction - Fast token/keyword extraction from post text
"""
import re
from typing import List

# Crypto tokens like $BTC, $ETH
TOKEN_REGEX = re.compile(r"\$[A-Za-z]{2,10}")

# Important keywords (case insensitive)
KEYWORDS = [
    "etf", "airdrop", "sec", "binance", "ton", "solana", "bitcoin", "eth",
    "btc", "ethereum", "coinbase", "kraken", "bybit", "okx", "whale",
    "pump", "dump", "bullish", "bearish", "moon", "crash", "hack",
    "exploit", "rugpull", "scam", "listing", "delist", "regulation",
    "staking", "defi", "nft", "memecoin", "altcoin", "mainnet", "testnet",
    "халвинг", "аирдроп", "листинг", "делист", "стейкинг", "кит"
]

KEYWORD_REGEX = re.compile(r"\b(" + "|".join(KEYWORDS) + r")\b", re.IGNORECASE)


def extract_topics(text: str) -> List[str]:
    """Extract topics from text - tokens ($BTC) and keywords"""
    if not text:
        return []
    
    normalized = set()
    
    # Extract $TOKEN patterns
    tokens = TOKEN_REGEX.findall(text)
    for t in tokens:
        normalized.add(t.upper())
    
    # Extract keywords
    keywords = KEYWORD_REGEX.findall(text)
    for w in keywords:
        normalized.add(w.upper())
    
    return list(normalized)
