# Telegram Intelligence Module v1.0.0

## 🧊 Status: FROZEN

**Standalone • Extractable • Contract-Safe**

---

## Quick Start

```python
from telegram_intel import TelegramModule, TelegramConfig

config = TelegramConfig(
    mongo_uri="mongodb://localhost:27017",
    session_string="...",  # MTProto session
    bot_token="..."        # Telegram Bot token
)

telegram = TelegramModule(config)

# Register routes
app.include_router(telegram.router)

# Start module
await telegram.start()

# On shutdown
await telegram.stop()
```

---

## Module Structure

```
telegram_intel/
├── __init__.py              # Public exports
├── __version__.py           # Version info (1.0.0)
├── module.py                # TelegramModule class
├── smoke_test.py            # Pre-extraction test
├── .env.contract            # Required env vars
│
├── contracts/               # Type contracts (FROZEN)
│   ├── types.py            # FeedPost, PostReactions, etc.
│   ├── api.py              # FeedResponse, ChannelResponse, etc.
│   └── config.py           # TelegramConfig
│
├── storage/                 # Database layer
│   └── __init__.py         # Collections, indexes
│
├── services/                # Business logic
├── workers/                 # Background tasks
├── bot/                     # Telegram bot handlers
└── api/                     # FastAPI routes
```

---

## Public API (FROZEN)

### Feed
```python
await telegram.get_feed(actor_id, page, limit, window_days)
await telegram.get_feed_stats(actor_id, hours)
await telegram.get_feed_summary(hours)
```

### Channel
```python
await telegram.get_channel(username)
await telegram.get_channels(limit, offset, sort_by)
```

### Watchlist
```python
await telegram.get_watchlist(actor_id)
await telegram.add_to_watchlist(username, actor_id)
await telegram.remove_from_watchlist(username, actor_id)
```

### Alerts & Digest
```python
await telegram.get_alerts(actor_id, limit)
await telegram.dispatch_alerts()
await telegram.run_digest(actor_id)
```

### Bot
```python
await telegram.get_bot_status()
```

---

## Data Contracts (FROZEN)

### FeedPost
```python
class FeedPost:
    messageId: int
    username: str
    date: str
    text: str
    views: int
    forwards: int
    replies: int
    reactions: PostReactions
    hasMedia: bool
    media: Optional[MediaPayload]
    feedScore: float
    isPinned: bool
    isRead: bool
```

### PostReactions
```python
class PostReactions:
    total: int
    items: List[ReactionItem]  # Full list
    top: List[ReactionItem]    # Top 3
    extraCount: int            # Items beyond top 3
```

---

## Collections (Namespace Isolated)

| Collection | Purpose |
|------------|---------|
| `tg_channel_states` | Channel profiles & metrics |
| `tg_posts` | Post content & metrics |
| `tg_media_assets` | Media file references |
| `tg_watchlist` | User watchlists |
| `tg_feed_state` | Pin/read states |
| `tg_alerts` | Generated alerts |
| `tg_actor_links` | Bot-linked users |
| `tg_delivery_outbox` | Pending bot messages |
| `tg_edge_events` | Channel mentions |
| `tg_members_history` | Growth tracking |

---

## Environment Contract

```bash
# Required
MONGO_URL=mongodb://localhost:27017
TG_SESSION_STRING=...
TG_BOT_TOKEN=...

# Optional
TG_MEDIA_PATH=/data/telegram_media
EMERGENT_LLM_KEY=...
```

---

## Extraction Checklist

Before extracting to new project:

- [ ] Run `python -m telegram_intel.smoke_test`
- [ ] Verify MTProto reconnect works
- [ ] Verify feed returns posts
- [ ] Verify media serves correctly
- [ ] Verify bot webhook works
- [ ] Copy `.env.contract` values

---

## Freeze Rules

After v1.0.0:

- ❌ Do not change FeedPost structure
- ❌ Do not change PostReactions format
- ❌ Do not change API response shapes
- ❌ Do not rename collections

If changes needed → create v2 contracts.

---

## Version History

| Version | Date | Status |
|---------|------|--------|
| 1.0.0 | 2026-02-25 | FROZEN |

---

## License

Internal use only.
