"""
Signal Trust Engine
Automatically calculates truthScore based on reports, source quality, and freshness
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
import math

logger = logging.getLogger(__name__)

# Trust score weights
WEIGHTS = {
    "reports": 0.40,      # Number of confirmations
    "source": 0.25,       # Source quality
    "freshness": 0.20,    # How recent
    "cluster": 0.15,      # Part of cluster
}

# Source quality scores
SOURCE_QUALITY = {
    "verified_channel": 1.0,
    "telegram_channel": 0.8,
    "user_report": 0.6,
    "manual_admin": 0.9,
    "unknown": 0.3,
}

# Report count to score mapping
REPORT_SCORES = {
    1: 0.25,
    2: 0.40,
    3: 0.55,
    4: 0.65,
    5: 0.75,
    6: 0.82,
    7: 0.88,
    8: 0.92,
}

# Signal status thresholds
STATUS_THRESHOLDS = {
    "raw": 0.0,
    "weak": 0.30,
    "medium": 0.50,
    "confirmed": 0.70,
}


class SignalTrustEngine:
    """Calculates and manages signal trust scores"""
    
    def __init__(self, db):
        self.db = db
        self.signals = db.geo_signals
        self.reports = db.geo_reports
    
    def calculate_truth_score(
        self,
        reports_count: int,
        source_type: str,
        created_at: datetime,
        in_cluster: bool = False
    ) -> float:
        """
        Calculate truth score for a signal
        
        Formula:
        truthScore = 
            reports_weight * 0.40 +
            source_weight * 0.25 +
            freshness_weight * 0.20 +
            cluster_weight * 0.15
        """
        # Reports weight (0-1)
        if reports_count >= 8:
            reports_score = 0.95
        else:
            reports_score = REPORT_SCORES.get(reports_count, 0.25)
        
        # Source weight (0-1)
        source_score = SOURCE_QUALITY.get(source_type, 0.3)
        
        # Freshness weight (0-1) - decays over time
        now = datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        
        age_hours = (now - created_at).total_seconds() / 3600
        # Full score for first 2 hours, then decay
        if age_hours <= 2:
            freshness_score = 1.0
        elif age_hours <= 6:
            freshness_score = 0.8
        elif age_hours <= 12:
            freshness_score = 0.6
        elif age_hours <= 24:
            freshness_score = 0.4
        else:
            freshness_score = max(0.1, 1.0 - (age_hours / 48))
        
        # Cluster weight (0 or 1)
        cluster_score = 1.0 if in_cluster else 0.0
        
        # Calculate final score
        truth_score = (
            reports_score * WEIGHTS["reports"] +
            source_score * WEIGHTS["source"] +
            freshness_score * WEIGHTS["freshness"] +
            cluster_score * WEIGHTS["cluster"]
        )
        
        return round(min(1.0, truth_score), 2)
    
    def get_status_from_score(self, truth_score: float) -> str:
        """Determine signal status from truth score"""
        if truth_score >= STATUS_THRESHOLDS["confirmed"]:
            return "confirmed"
        elif truth_score >= STATUS_THRESHOLDS["medium"]:
            return "medium"
        elif truth_score >= STATUS_THRESHOLDS["weak"]:
            return "weak"
        else:
            return "raw"
    
    async def update_signal_trust(self, signal_id: str) -> Dict[str, Any]:
        """Recalculate and update signal trust score"""
        signal = await self.signals.find_one({"signalId": signal_id})
        if not signal:
            return {"ok": False, "error": "Signal not found"}
        
        # Count reports for this signal
        reports_count = await self.reports.count_documents({
            "signalId": signal_id,
            "type": "confirm"
        })
        
        # Add original report
        reports_count += 1
        
        # Check if in cluster
        in_cluster = signal.get("clusterId") is not None
        
        # Calculate new score
        truth_score = self.calculate_truth_score(
            reports_count=reports_count,
            source_type=signal.get("sourceType", "unknown"),
            created_at=signal.get("createdAt", datetime.now(timezone.utc)),
            in_cluster=in_cluster
        )
        
        status = self.get_status_from_score(truth_score)
        
        # Update signal
        await self.signals.update_one(
            {"signalId": signal_id},
            {
                "$set": {
                    "truthScore": truth_score,
                    "status": status,
                    "reportsCount": reports_count,
                    "updatedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        logger.info(f"Signal {signal_id}: truthScore={truth_score}, status={status}")
        
        return {
            "ok": True,
            "signalId": signal_id,
            "truthScore": truth_score,
            "status": status,
            "reportsCount": reports_count
        }
    
    async def add_report(
        self,
        signal_id: str,
        user_id: str,
        report_type: str = "confirm"
    ) -> Dict[str, Any]:
        """Add a report (confirm/dismiss) for a signal"""
        now = datetime.now(timezone.utc)
        
        # Check for duplicate
        existing = await self.reports.find_one({
            "signalId": signal_id,
            "userId": user_id
        })
        
        if existing:
            return {"ok": False, "error": "Already reported"}
        
        # Add report
        report = {
            "signalId": signal_id,
            "userId": user_id,
            "type": report_type,  # confirm, dismiss, fake
            "createdAt": now
        }
        
        await self.reports.insert_one(report)
        
        # Recalculate trust score
        result = await self.update_signal_trust(signal_id)
        
        return result
    
    async def decay_old_signals(self, hours: int = 24) -> int:
        """Decay truth scores for old signals"""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Find signals that need decay
        signals = await self.signals.find({
            "createdAt": {"$lt": cutoff},
            "status": {"$ne": "dismissed"}
        }).to_list(1000)
        
        updated = 0
        for signal in signals:
            result = await self.update_signal_trust(signal.get("signalId"))
            if result.get("ok"):
                updated += 1
        
        logger.info(f"Decayed {updated} signals")
        return updated
    
    async def auto_confirm_high_trust(self, threshold: float = 0.75) -> int:
        """Auto-confirm signals with high trust scores"""
        result = await self.signals.update_many(
            {
                "truthScore": {"$gte": threshold},
                "status": {"$ne": "confirmed"}
            },
            {
                "$set": {
                    "status": "confirmed",
                    "autoConfirmed": True,
                    "updatedAt": datetime.now(timezone.utc)
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Auto-confirmed {result.modified_count} signals")
        
        return result.modified_count
