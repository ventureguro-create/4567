"""
Intelligence Scheduler
Background worker that runs all intelligence engines
- Probability Engine (hourly)
- Fusion Engine (every minute)
- Decay Worker (every minute)
"""
import asyncio
import logging
from datetime import datetime, timezone

from .probability_repository import ProbabilityRepository
from .probability_engine import ProbabilityEngine
from .fusion_repository import FusionRepository
from .fusion_engine import FusionEngine
from .signal_decay import DecayWorker

logger = logging.getLogger(__name__)


class IntelligenceScheduler:
    """
    Master scheduler for all geo intelligence processes.
    
    Runs:
    - Fusion + Decay: every 60 seconds
    - Probability: every 60 minutes
    """
    
    def __init__(self, db):
        self.db = db
        self.running = False
        self.cycle_count = 0
        self.last_probability_run = None
    
    async def run_fusion_cycle(self):
        """Run fusion and decay engines"""
        try:
            # Fusion
            fusion_repo = FusionRepository(self.db)
            fusion_engine = FusionEngine(fusion_repo)
            fusion_result = await fusion_engine.rebuild()
            
            # Decay
            decay_worker = DecayWorker(self.db)
            decay_result = await decay_worker.run_once()
            
            return {
                "fusion": fusion_result,
                "decay": decay_result
            }
        except Exception as e:
            logger.error(f"Fusion cycle error: {e}")
            return {"error": str(e)}
    
    async def run_probability_cycle(self):
        """Run probability engine"""
        try:
            prob_repo = ProbabilityRepository(self.db)
            prob_engine = ProbabilityEngine(prob_repo)
            result = await prob_engine.rebuild()
            self.last_probability_run = datetime.now(timezone.utc)
            return result
        except Exception as e:
            logger.error(f"Probability cycle error: {e}")
            return {"error": str(e)}
    
    async def run(self):
        """Main scheduler loop"""
        logger.info("Intelligence Scheduler started")
        self.running = True
        
        # Initial probability run
        await self.run_probability_cycle()
        
        while self.running:
            try:
                self.cycle_count += 1
                
                # Fusion + Decay every cycle
                await self.run_fusion_cycle()
                
                # Probability every 60 cycles (60 minutes)
                if self.cycle_count % 60 == 0:
                    await self.run_probability_cycle()
                
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(60)
    
    def stop(self):
        """Stop scheduler"""
        self.running = False
        logger.info(f"Intelligence Scheduler stopped after {self.cycle_count} cycles")


# Global instance
_scheduler: IntelligenceScheduler = None


async def start_intelligence_scheduler(db):
    """Start intelligence scheduler in background"""
    global _scheduler
    _scheduler = IntelligenceScheduler(db)
    asyncio.create_task(_scheduler.run())
    return _scheduler


def get_intelligence_scheduler():
    """Get scheduler instance"""
    return _scheduler
