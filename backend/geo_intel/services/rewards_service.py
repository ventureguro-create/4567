"""
Rewards Service - Система награждения за підтверджені сигнали

Підписка: $2.00/місяць

Розподіл:
- 30% реферальна програма: $0.60
- 30% винагорода за сигнали: $0.60 (пул на місяць)

Винагороди:
- $0.30 базова за підтверджений сигнал
- +$0.10 бонус за фото
- $0.05 за підтвердження чужого сигналу
- Бонус за серію (3 дні поспіль): +$0.15

Вивід: через Telegram Stars
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from decimal import Decimal, ROUND_HALF_UP

logger = logging.getLogger(__name__)

# Subscription pricing
SUBSCRIPTION_PRICE = Decimal("2.00")          # Місячна підписка
REFERRAL_PERCENT = Decimal("0.30")            # 30% реферальна
REWARDS_POOL_PERCENT = Decimal("0.30")        # 30% на винагороди

# Reward amounts in USD (новая математика)
REWARD_SIGNAL_CREATED = Decimal("0.30")       # Базова за підтверджений сигнал
REWARD_SIGNAL_CONFIRMED = Decimal("0.05")     # За підтвердження чужого сигналу
REWARD_STREAK_BONUS = Decimal("0.15")         # Бонус за серію з 3 днів
REWARD_PHOTO_BONUS = Decimal("0.10")          # Бонус за фото
REWARD_INSTANT_BONUS = Decimal("0.10")        # Бонус за точну геолокацію (Миттєво)

# Confirmation thresholds
CONFIDENCE_LEVELS = {
    1: 0.3,   # 1 user - weak
    2: 0.45,  # 2 users
    3: 0.6,   # 3 users - confirmed
    4: 0.75,  # 4 users
    5: 0.9,   # 5+ users - high confidence
}

# Minimum withdrawal
MIN_WITHDRAWAL_USD = Decimal("1.00")

# Stars conversion (1 Star ≈ $0.02)
USD_TO_STARS_RATE = 50  # 50 stars = $1


class RewardsService:
    """Manages user rewards and signal confirmations"""
    
    def __init__(self, db):
        self.db = db
        self.balances = db.geo_user_balances
        self.transactions = db.geo_reward_transactions
        self.confirmations = db.geo_signal_confirmations
    
    async def ensure_indexes(self):
        """Create necessary indexes"""
        await self.balances.create_index("actorId", unique=True)
        await self.transactions.create_index("actorId")
        await self.transactions.create_index("createdAt")
        await self.transactions.create_index([("actorId", 1), ("type", 1)])
        await self.confirmations.create_index([("signalId", 1), ("actorId", 1)], unique=True)
        await self.confirmations.create_index("signalId")
    
    async def get_balance(self, actor_id: str) -> Dict[str, Any]:
        """Get user's current balance"""
        doc = await self.balances.find_one({"actorId": actor_id})
        
        if not doc:
            doc = await self._create_balance(actor_id)
        
        balance = Decimal(str(doc.get("balance", 0)))
        pending = Decimal(str(doc.get("pending", 0)))
        total_earned = Decimal(str(doc.get("totalEarned", 0)))
        
        return {
            "actorId": actor_id,
            "balance": float(balance),
            "balanceStars": int(balance * USD_TO_STARS_RATE),
            "pending": float(pending),
            "totalEarned": float(total_earned),
            "canWithdraw": balance >= MIN_WITHDRAWAL_USD,
            "minWithdrawal": float(MIN_WITHDRAWAL_USD)
        }
    
    async def _create_balance(self, actor_id: str) -> Dict[str, Any]:
        """Create balance record for new user"""
        now = datetime.now(timezone.utc)
        doc = {
            "actorId": actor_id,
            "balance": 0.0,
            "pending": 0.0,
            "totalEarned": 0.0,
            "totalWithdrawn": 0.0,
            "signalsCreated": 0,
            "signalsConfirmed": 0,
            "currentStreak": 0,
            "lastRewardAt": None,
            "createdAt": now,
            "updatedAt": now
        }
        await self.balances.insert_one(doc)
        return doc
    
    async def reward_signal_created(
        self,
        actor_id: str,
        signal_id: str,
        has_photo: bool = False
    ) -> Dict[str, Any]:
        """
        Award reward for creating a confirmed signal.
        Called when admin approves or crowd confirms the signal.
        """
        now = datetime.now(timezone.utc)
        
        # Calculate reward
        reward = REWARD_SIGNAL_CREATED
        if has_photo:
            reward += REWARD_PHOTO_BONUS
        
        # Check streak bonus
        balance_doc = await self.balances.find_one({"actorId": actor_id})
        if balance_doc:
            last_reward = balance_doc.get("lastRewardAt")
            current_streak = balance_doc.get("currentStreak", 0)
            
            if last_reward:
                days_diff = (now - last_reward).days
                if days_diff == 1:
                    current_streak += 1
                elif days_diff > 1:
                    current_streak = 1
                # Same day doesn't break streak
            else:
                current_streak = 1
            
            # Award streak bonus at day 3
            if current_streak == 3:
                reward += REWARD_STREAK_BONUS
                logger.info(f"Streak bonus awarded to {actor_id}: {REWARD_STREAK_BONUS}")
        else:
            current_streak = 1
        
        # Record transaction
        tx = {
            "actorId": actor_id,
            "type": "signal_created",
            "amount": float(reward),
            "signalId": signal_id,
            "hasPhoto": has_photo,
            "streak": current_streak,
            "createdAt": now
        }
        await self.transactions.insert_one(tx)
        
        # Update balance
        await self.balances.update_one(
            {"actorId": actor_id},
            {
                "$inc": {
                    "balance": float(reward),
                    "totalEarned": float(reward),
                    "signalsCreated": 1
                },
                "$set": {
                    "currentStreak": current_streak,
                    "lastRewardAt": now,
                    "updatedAt": now
                }
            },
            upsert=True
        )
        
        logger.info(f"Reward {reward} USD for signal creation to {actor_id}")
        
        return {
            "ok": True,
            "reward": float(reward),
            "rewardStars": int(reward * USD_TO_STARS_RATE),
            "streak": current_streak,
            "streakBonus": current_streak == 3
        }
    
    async def reward_confirmation(
        self,
        actor_id: str,
        signal_id: str,
        signal_creator_id: str
    ) -> Dict[str, Any]:
        """
        Award reward for confirming someone else's signal.
        Also gives bonus to signal creator.
        """
        now = datetime.now(timezone.utc)
        
        # Check if already confirmed by this user
        existing = await self.confirmations.find_one({
            "signalId": signal_id,
            "actorId": actor_id
        })
        
        if existing:
            return {"ok": False, "error": "Ви вже підтвердили цей сигнал"}
        
        # Record confirmation
        await self.confirmations.insert_one({
            "signalId": signal_id,
            "actorId": actor_id,
            "createdAt": now
        })
        
        # Count total confirmations
        confirm_count = await self.confirmations.count_documents({"signalId": signal_id})
        
        # Update signal confidence
        new_confidence = self._calculate_confidence(confirm_count)
        await self.db.tg_crowd_signals.update_one(
            {"_id": signal_id},
            {
                "$set": {"confidence": new_confidence},
                "$inc": {"confirmations": 1}
            }
        )
        
        # Reward confirmer
        reward = REWARD_SIGNAL_CONFIRMED
        
        await self.transactions.insert_one({
            "actorId": actor_id,
            "type": "signal_confirmed",
            "amount": float(reward),
            "signalId": signal_id,
            "createdAt": now
        })
        
        await self.balances.update_one(
            {"actorId": actor_id},
            {
                "$inc": {
                    "balance": float(reward),
                    "totalEarned": float(reward),
                    "signalsConfirmed": 1
                },
                "$set": {"updatedAt": now}
            },
            upsert=True
        )
        
        # Bonus to signal creator (if different person)
        creator_bonus = Decimal("0.005")  # $0.005 per confirmation
        if signal_creator_id and signal_creator_id != actor_id:
            await self.transactions.insert_one({
                "actorId": signal_creator_id,
                "type": "confirmation_received",
                "amount": float(creator_bonus),
                "signalId": signal_id,
                "confirmedBy": actor_id,
                "createdAt": now
            })
            
            await self.balances.update_one(
                {"actorId": signal_creator_id},
                {
                    "$inc": {
                        "balance": float(creator_bonus),
                        "totalEarned": float(creator_bonus)
                    },
                    "$set": {"updatedAt": now}
                },
                upsert=True
            )
            
            # Update trust score
            from .trust_score_service import TrustScoreService
            trust_svc = TrustScoreService(self.db)
            await trust_svc.add_confirmation_received(signal_creator_id)
        
        logger.info(f"Confirmation reward: {actor_id} confirmed signal {signal_id}, new confidence: {new_confidence}")
        
        return {
            "ok": True,
            "reward": float(reward),
            "rewardStars": int(reward * USD_TO_STARS_RATE),
            "confirmations": confirm_count,
            "newConfidence": new_confidence,
            "signalStrength": self._get_strength_label(confirm_count)
        }
    
    def _calculate_confidence(self, confirm_count: int) -> float:
        """Calculate confidence based on confirmation count"""
        if confirm_count >= 5:
            return CONFIDENCE_LEVELS[5]
        return CONFIDENCE_LEVELS.get(confirm_count, 0.3)
    
    def _get_strength_label(self, confirm_count: int) -> str:
        """Get human-readable strength label"""
        if confirm_count >= 5:
            return "🔥 Високий"
        elif confirm_count >= 3:
            return "✅ Підтверджено"
        elif confirm_count >= 2:
            return "👁 Помічено"
        return "⚪ Слабкий"
    
    async def get_signal_confirmations(self, signal_id: str) -> Dict[str, Any]:
        """Get confirmation info for a signal"""
        count = await self.confirmations.count_documents({"signalId": signal_id})
        
        return {
            "signalId": signal_id,
            "confirmations": count,
            "confidence": self._calculate_confidence(count),
            "strength": self._get_strength_label(count)
        }
    
    async def withdraw(
        self,
        actor_id: str,
        method: str = "stars"
    ) -> Dict[str, Any]:
        """
        Request withdrawal of balance.
        Converts to Telegram Stars.
        """
        balance = await self.get_balance(actor_id)
        
        if not balance["canWithdraw"]:
            return {
                "ok": False,
                "error": f"Мінімальна сума для виведення: ${MIN_WITHDRAWAL_USD}"
            }
        
        amount = Decimal(str(balance["balance"]))
        stars = int(amount * USD_TO_STARS_RATE)
        now = datetime.now(timezone.utc)
        
        # Record withdrawal transaction
        await self.transactions.insert_one({
            "actorId": actor_id,
            "type": "withdrawal",
            "amount": -float(amount),
            "stars": stars,
            "method": method,
            "status": "pending",
            "createdAt": now
        })
        
        # Update balance
        await self.balances.update_one(
            {"actorId": actor_id},
            {
                "$set": {"balance": 0.0, "updatedAt": now},
                "$inc": {"totalWithdrawn": float(amount)}
            }
        )
        
        logger.info(f"Withdrawal requested: {actor_id} - ${amount} = {stars} Stars")
        
        return {
            "ok": True,
            "amount": float(amount),
            "stars": stars,
            "method": method,
            "status": "pending"
        }
    
    async def get_transaction_history(
        self,
        actor_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get user's transaction history"""
        cursor = self.transactions.find(
            {"actorId": actor_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit)
        
        return [doc async for doc in cursor]
    
    async def get_top_earners(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top earners leaderboard"""
        cursor = self.balances.find(
            {"totalEarned": {"$gt": 0}},
            {"_id": 0, "actorId": 1, "totalEarned": 1, "signalsCreated": 1, "signalsConfirmed": 1}
        ).sort("totalEarned", -1).limit(limit)
        
        results = []
        rank = 1
        async for doc in cursor:
            results.append({
                "rank": rank,
                "actorId": doc.get("actorId"),
                "totalEarned": doc.get("totalEarned", 0),
                "totalEarnedStars": int(doc.get("totalEarned", 0) * USD_TO_STARS_RATE),
                "signalsCreated": doc.get("signalsCreated", 0),
                "signalsConfirmed": doc.get("signalsConfirmed", 0)
            })
            rank += 1
        
        return results
    
    def format_balance_message(self, balance: Dict[str, Any]) -> str:
        """Format balance info for Telegram message"""
        usd = balance["balance"]
        stars = balance["balanceStars"]
        total = balance["totalEarned"]
        
        msg = (
            f"💰 *Ваш баланс*\n\n"
            f"Доступно: ${usd:.2f} ({stars} ⭐)\n"
            f"Всього зароблено: ${total:.2f}\n\n"
        )
        
        if balance["canWithdraw"]:
            msg += "✅ Можна вивести"
        else:
            msg += f"⚠️ Мінімум для виведення: ${balance['minWithdrawal']:.2f}"
        
        return msg
