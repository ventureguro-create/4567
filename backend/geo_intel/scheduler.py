"""
Geo Intel Scheduler
Background worker for building geo events
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class GeoScheduler:
    """Background scheduler for geo event building"""
    
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.running = False
        self._task = None
    
    def start(self):
        """Start the scheduler loop"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Geo scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Geo scheduler stopped")
    
    async def _loop(self):
        """Main scheduler loop"""
        from .services.builder import build_geo_events_for_channel
        
        while self.running:
            try:
                # Get channels that need scanning
                channels = await self.db.tg_radar_channels.find({
                    "enabled": True
                }).sort("lastScanAt", 1).limit(10).to_list(10)
                
                for channel in channels:
                    if not self.running:
                        break
                    
                    username = channel["username"]
                    logger.info(f"Geo scheduler: scanning {username}")
                    
                    try:
                        await build_geo_events_for_channel(
                            self.db,
                            username=username,
                            days=self.config.lookback_days
                        )
                    except Exception as e:
                        logger.error(f"Geo scan error for {username}: {e}")
                    
                    # Small delay between channels
                    await asyncio.sleep(5)
                
                # Wait before next cycle
                await asyncio.sleep(1800)  # 30 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Geo scheduler error: {e}")
                await asyncio.sleep(60)
