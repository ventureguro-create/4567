"""Language Detection & Crypto Relevance Gate"""
import re
from typing import List, Dict, Any, Set
from collections import Counter


def detect_lang_and_crypto(posts: List[Dict], opts: Dict[str, Any] = None) -> Dict[str, Any]:
    """Detect language (RU/UK) and crypto relevance from posts"""
    opts = opts or {}
    allow = set(str(opts.get('allow', 'ru,uk,mixed')).split(','))
    min_texts = int(opts.get('minTexts', 10))
    crypto_min_score = float(opts.get('cryptoMinScore', 0.08))
    
    texts = [
        _normalize_text(p.get('text', ''))
        for p in posts
        if len(p.get('text', '')) >= 20
    ][:60]
    
    if len(texts) < min_texts:
        return {
            'lang': 'unknown',
            'langConfidence': 0,
            'cryptoRelevanceScore': 0,
            'cryptoHits': 0,
            'langGate': 'UNKNOWN',
            'topicGate': 'UNKNOWN',
            'allowList': list(allow),
            'cryptoMinScore': crypto_min_score,
        }
    
    joined = ' '.join(texts)
    cyr, lat = _script_counts(joined)
    
    # UK markers: ґ є ї і
    uk_markers = _count_chars(joined, 'ґєїі')
    # RU markers: ёъыэ
    ru_markers = _count_chars(joined, 'ёъыэ')
    
    cyr_ratio = cyr / max(1, cyr + lat)
    uk_ratio = uk_markers / max(1, cyr)
    ru_ratio = ru_markers / max(1, cyr)
    
    lang = 'other'
    lang_confidence = 0
    
    if cyr_ratio >= 0.6:
        if uk_ratio >= 0.01 and ru_ratio < 0.006:
            lang = 'uk'
            lang_confidence = min(1, 0.6 + uk_ratio * 30)
        elif ru_ratio >= 0.008 and uk_ratio < 0.006:
            lang = 'ru'
            lang_confidence = min(1, 0.6 + ru_ratio * 25)
        else:
            lang = 'mixed'
            lang_confidence = min(1, 0.55 + max(uk_ratio, ru_ratio) * 15)
    else:
        lang = 'other'
        lang_confidence = min(1, 1 - cyr_ratio)
    
    # Crypto relevance
    crypto_score, crypto_hits = _crypto_score(texts)
    
    lang_gate = 'PASS' if lang in allow else 'FAIL'
    topic_gate = 'PASS' if crypto_score >= crypto_min_score else 'FAIL'
    
    return {
        'lang': lang,
        'langConfidence': round(lang_confidence, 3),
        'cryptoRelevanceScore': round(crypto_score, 4),
        'cryptoHits': crypto_hits,
        'langGate': lang_gate,
        'topicGate': topic_gate,
        'allowList': list(allow),
        'cryptoMinScore': crypto_min_score,
    }


KEYWORDS = [
    'bitcoin', 'btc', 'ethereum', 'eth', 'solana', 'sol', 'ton', 'trx', 'usdt', 'usdc',
    'airdrop', 'drop', 'alpha', 'листинг', 'listing', 'ido', 'ieo', 'tge', 'whitelist',
    'фарм', 'farm', 'restake', 're-stake', 'staking', 'стейк', 'стейкинг',
    'dex', 'cex', 'binance', 'bybit', 'okx', 'kucoin',
    'перп', 'perp', 'funding', 'фандинг', 'лонг', 'шорт', 'leverage', 'плечо',
    'onchain', 'ончейн', 'bridge', 'бридж', 'zk', 'rollup', 'layer2', 'l2',
    'nft', 'mint', 'минт', 'floor', 'флор', 'collection', 'коллекция',
    'defi', 'lend', 'borrow', 'apy', 'yield',
    'token', 'токен', 'токены', 'tokenomics', 'токеномика', 'эмиссия',
    'wallet', 'кошелек', 'seed', 'сид', 'private key', 'приватный ключ',
]

TICKER_RE = re.compile(r'\$[A-Z]{2,10}\b')


def _crypto_score(texts: List[str]) -> tuple:
    """Calculate crypto relevance score"""
    hits = 0
    ticker_hits = 0
    
    for t in texts:
        lc = t.lower()
        
        # ticker mentions
        m = TICKER_RE.findall(lc.upper())
        ticker_hits += len(m)
        
        # keyword hits
        for k in KEYWORDS:
            if k in lc:
                hits += 1
    
    base = hits / max(1, len(texts))
    ticker_boost = min(0.25, ticker_hits / max(1, len(texts)) * 0.05)
    
    score = min(1, base * 0.06 + ticker_boost)
    return score, hits + ticker_hits


def _normalize_text(s: str) -> str:
    return re.sub(r'\s+', ' ', s).strip()


def _script_counts(s: str) -> tuple:
    cyr = 0
    lat = 0
    for ch in s:
        code = ord(ch)
        # Cyrillic block
        if 0x0400 <= code <= 0x04FF or 0x0500 <= code <= 0x052F:
            cyr += 1
        # Latin basic
        if 0x0041 <= code <= 0x007A:
            lat += 1
    return cyr, lat


def _count_chars(s: str, charset: str) -> int:
    charset_set = set(charset)
    return sum(1 for ch in s if ch in charset_set)
