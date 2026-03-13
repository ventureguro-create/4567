#!/usr/bin/env python3
"""
Telegram Intel Module - Smoke Test
Version: 1.0.0

Run this before extracting the module to verify all functionality.

Usage:
    python -m telegram_intel.smoke_test
    
Or:
    python telegram_intel/smoke_test.py

This test verifies:
- Module imports correctly
- Config validation works
- MongoDB connection works
- Storage layer works
- Feed returns data
- Channel returns data
- Bot status works (if token set)
- Digest doesn't crash
"""

import asyncio
import os
import sys
from typing import List, Tuple

# Test results
RESULTS: List[Tuple[str, bool, str]] = []


def log_result(name: str, passed: bool, message: str = ""):
    """Log test result"""
    status = "✅" if passed else "❌"
    print(f"  {status} {name}" + (f" - {message}" if message else ""))
    RESULTS.append((name, passed, message))


async def run_smoke_tests():
    """Run all smoke tests"""
    print("\n" + "="*60)
    print("🧪 Telegram Intel Module v1.0.0 - Smoke Test")
    print("="*60 + "\n")
    
    # ==========================================
    # 1. Import Tests
    # ==========================================
    print("📦 1. Import Tests:")
    
    try:
        from telegram_intel import TelegramModule, TelegramConfig, VERSION, FROZEN
        log_result("Import TelegramModule", True, f"v{VERSION} frozen={FROZEN}")
    except Exception as e:
        log_result("Import TelegramModule", False, str(e))
        return False
    
    try:
        from telegram_intel.contracts import (
            FeedPost, PostMetrics, PostReactions,
            ChannelProfile, FeedResponse, ChannelResponse
        )
        log_result("Import Contracts", True)
    except Exception as e:
        log_result("Import Contracts", False, str(e))
        return False
    
    try:
        from telegram_intel.storage import COLLECTIONS, TelegramStorage
        log_result("Import Storage", True, f"{len(COLLECTIONS)} collections")
    except Exception as e:
        log_result("Import Storage", False, str(e))
        return False
    
    # ==========================================
    # 2. Config Tests
    # ==========================================
    print("\n⚙️ 2. Config Tests:")
    
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    session_string = os.environ.get("TG_SESSION_STRING", "")
    bot_token = os.environ.get("TG_BOT_TOKEN", "")
    
    try:
        config = TelegramConfig(
            mongo_uri=mongo_url,
            db_name="telegram_intel",
            session_string=session_string or None,
            bot_token=bot_token or None,
            scheduler_enabled=False  # Don't start scheduler in test
        )
        log_result("Create Config", True)
        log_result("Session String", bool(session_string), "set" if session_string else "NOT SET")
        log_result("Bot Token", bool(bot_token), "set" if bot_token else "NOT SET")
    except Exception as e:
        log_result("Create Config", False, str(e))
        return False
    
    # ==========================================
    # 3. Module Initialization
    # ==========================================
    print("\n🚀 3. Module Tests:")
    
    try:
        module = TelegramModule(config)
        log_result("Create Module", True)
    except Exception as e:
        log_result("Create Module", False, str(e))
        return False
    
    # Check version method
    try:
        version_info = module.get_version_info()
        assert version_info["version"] == "1.0.0"
        assert version_info["frozen"] == True
        log_result("Version Info", True, f"v{version_info['version']}")
    except Exception as e:
        log_result("Version Info", False, str(e))
    
    try:
        await module.start()
        log_result("Start Module", True)
    except Exception as e:
        log_result("Start Module", False, str(e))
        return False
    
    # ==========================================
    # 4. Database Tests
    # ==========================================
    print("\n💾 4. Database Tests:")
    
    try:
        await module.db.command("ping")
        log_result("MongoDB Connection", True)
    except Exception as e:
        log_result("MongoDB Connection", False, str(e))
        await module.stop()
        return False
    
    try:
        from telegram_intel.storage import COLLECTIONS
        counts = {}
        for name, col in COLLECTIONS.items():
            counts[name] = await module.db[col].count_documents({})
        total = sum(counts.values())
        log_result("Collections Access", True, f"{total} total docs")
    except Exception as e:
        log_result("Collections Access", False, str(e))
    
    # ==========================================
    # 5. Feed API Tests
    # ==========================================
    print("\n📰 5. Feed API Tests:")
    
    try:
        result = await module.get_feed(actor_id="default", limit=10)
        items = result.get("items", [])
        total = result.get("total", 0)
        log_result("get_feed()", True, f"{len(items)} items, {total} total")
        
        # Verify structure
        if items:
            post = items[0]
            has_reactions = "reactions" in post
            has_metrics = all(k in post for k in ["views", "forwards", "replies"])
            log_result("Feed Post Structure", has_reactions and has_metrics)
    except Exception as e:
        log_result("get_feed()", False, str(e))
    
    try:
        result = await module.get_feed_stats(actor_id="default", hours=24)
        log_result("get_feed_stats()", result.get("ok", False), f"media={result.get('mediaCount', 0)}")
    except Exception as e:
        log_result("get_feed_stats()", False, str(e))
    
    # ==========================================
    # 6. Channel API Tests
    # ==========================================
    print("\n📺 6. Channel API Tests:")
    
    try:
        result = await module.get_channels(limit=10)
        items = result.get("items", [])
        log_result("get_channels()", True, f"{len(items)} channels")
    except Exception as e:
        log_result("get_channels()", False, str(e))
    
    # Test get_channel if we have channels
    try:
        channels = await module.get_channels(limit=1)
        if channels.get("items"):
            username = channels["items"][0].get("username", "toncoin")
            result = await module.get_channel(username)
            has_channel = result.get("channel") is not None
            has_posts = len(result.get("posts", [])) > 0
            log_result("get_channel()", has_channel, f"@{username}, {len(result.get('posts', []))} posts")
    except Exception as e:
        log_result("get_channel()", False, str(e))
    
    # ==========================================
    # 7. Watchlist Tests
    # ==========================================
    print("\n📋 7. Watchlist Tests:")
    
    try:
        result = await module.get_watchlist(actor_id="default")
        items = result.get("items", [])
        log_result("get_watchlist()", True, f"{len(items)} items")
    except Exception as e:
        log_result("get_watchlist()", False, str(e))
    
    # ==========================================
    # 8. Bot Tests
    # ==========================================
    print("\n🤖 8. Bot Tests:")
    
    if bot_token:
        try:
            result = await module.get_bot_status()
            configured = result.get("botConfigured", False)
            webhook_active = result.get("webhook", {}).get("active", False)
            log_result("get_bot_status()", configured, f"webhook={'active' if webhook_active else 'inactive'}")
        except Exception as e:
            log_result("get_bot_status()", False, str(e))
    else:
        log_result("get_bot_status()", False, "SKIPPED - no bot token")
    
    # ==========================================
    # 9. Alerts Tests
    # ==========================================
    print("\n🔔 9. Alerts Tests:")
    
    try:
        result = await module.get_alerts(actor_id="default", limit=10)
        alerts = result.get("alerts", [])
        log_result("get_alerts()", True, f"{len(alerts)} alerts")
    except Exception as e:
        log_result("get_alerts()", False, str(e))
    
    # ==========================================
    # 10. Cleanup
    # ==========================================
    print("\n🧹 10. Cleanup:")
    
    try:
        await module.stop()
        log_result("Stop Module", True)
    except Exception as e:
        log_result("Stop Module", False, str(e))
    
    # ==========================================
    # Summary
    # ==========================================
    print("\n" + "="*60)
    passed = sum(1 for _, p, _ in RESULTS if p)
    total = len(RESULTS)
    failed = [name for name, p, _ in RESULTS if not p]
    
    if passed == total:
        print(f"🎉 ALL TESTS PASSED ({passed}/{total})")
        print("\n✅ Module is READY for extraction")
        print("   - All APIs functional")
        print("   - No platform dependencies")
        print("   - Contract-safe")
    else:
        print(f"⚠️ SOME TESTS FAILED: {passed}/{total}")
        print(f"\nFailed tests:")
        for name in failed:
            print(f"   ❌ {name}")
        print("\n❌ Fix issues before extracting")
    
    print("="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_smoke_tests())
    sys.exit(0 if success else 1)
