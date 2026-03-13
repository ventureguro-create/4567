"""
Geo Intel Module - Main Entry Point
Completely isolated from telegram_intel
"""
import os
import logging
from dataclasses import dataclass
from fastapi import APIRouter

from .router import build_geo_router
from .storage.indexes import ensure_geo_indexes
from .__version__ import VERSION

logger = logging.getLogger(__name__)


@dataclass
class GeoConfig:
    """Geo module configuration"""
    default_city: str = "Kyiv, Ukraine"
    lookback_days: int = 7
    enable_scheduler: bool = False
    max_events_per_run: int = 1000
    denylist_enabled: bool = True
    
    @classmethod
    def from_env(cls):
        return cls(
            default_city=os.getenv("GEO_DEFAULT_CITY", "Kyiv, Ukraine"),
            lookback_days=int(os.getenv("GEO_LOOKBACK_DAYS", "7")),
            enable_scheduler=os.getenv("GEO_ENABLE_SCHEDULER", "0") == "1",
            max_events_per_run=int(os.getenv("GEO_MAX_EVENTS_PER_RUN", "1000")),
            denylist_enabled=os.getenv("GEO_DENYLIST_ENABLED", "1") == "1"
        )


class GeoModule:
    """
    Geo Intelligence Module
    
    Completely isolated from telegram_intel.
    Only reads tg_posts (read-only), writes to tg_geo_events.
    """
    
    def __init__(self, db, config: GeoConfig = None):
        self.db = db
        self.config = config or GeoConfig.from_env()
        self.router: APIRouter = build_geo_router(db, self.config)
        self._started = False
    
    async def start(self):
        """Initialize module (indexes, scheduler, bot)"""
        if self._started:
            return
        
        logger.info(f"Starting Geo Intel Module v{VERSION}")
        
        # Create indexes
        await ensure_geo_indexes(self.db)
        
        # Start Telegram bot for alerts
        try:
            from .services.bot import start_bot
            await start_bot(self.db)
            logger.info("Geo Radar Bot started")
        except Exception as e:
            logger.warning(f"Bot start failed (non-critical): {e}")
        
        # Start alert scheduler
        try:
            from .services.scheduler import start_scheduler
            await start_scheduler(self.db)
            logger.info("Geo Alert Scheduler started")
        except Exception as e:
            logger.warning(f"Alert scheduler start failed (non-critical): {e}")
        
        # Start intelligence scheduler (fusion, decay, probability)
        try:
            from .services.intelligence_scheduler import start_intelligence_scheduler
            await start_intelligence_scheduler(self.db)
            logger.info("Intelligence Scheduler started")
        except Exception as e:
            logger.warning(f"Intelligence scheduler start failed (non-critical): {e}")
        
        # Initialize geo session indexes
        try:
            from .services.geo_session_service import ensure_session_indexes
            from .services.event_matcher import ensure_matcher_indexes
            await ensure_session_indexes(self.db)
            await ensure_matcher_indexes(self.db)
            logger.info("Geo Session indexes created")
        except Exception as e:
            logger.warning(f"Geo session indexes failed (non-critical): {e}")
        
        # Start geo event scheduler if enabled
        if self.config.enable_scheduler:
            from .scheduler import GeoScheduler
            self.scheduler = GeoScheduler(self.db, self.config)
            self.scheduler.start()
            logger.info("Geo event scheduler started")
        
        self._started = True
        logger.info("Geo Intel Module started")
    
    async def stop(self):
        """Stop module"""
        if hasattr(self, 'scheduler'):
            self.scheduler.stop()
        self._started = False
        logger.info("Geo Intel Module stopped")
    
    def version(self):
        """Get module version"""
        return {"version": VERSION, "frozen": False}
