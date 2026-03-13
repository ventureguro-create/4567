"""
Wallet Service - User balance and transactions
Handles referral earnings and withdrawal requests
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Constants
MIN_WITHDRAWAL_USD = 10.0  # Minimum $10 to withdraw
WITHDRAWAL_FEE_PERCENT = 0  # No fee for now


class WalletService:
    """User wallet service"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_or_create_wallet(self, user_id: str) -> Dict[str, Any]:
        """Get or create user wallet"""
        wallet = await self.db.wallets.find_one({"userId": user_id})
        
        if not wallet:
            wallet = {
                "userId": user_id,
                "referralBalance": 0.0,
                "pendingBalance": 0.0,
                "totalEarned": 0.0,
                "totalWithdrawn": 0.0,
                "currency": "USD",
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc)
            }
            await self.db.wallets.insert_one(wallet)
            wallet.pop("_id", None)
        else:
            wallet.pop("_id", None)
        
        return wallet
    
    async def get_balance(self, user_id: str) -> Dict[str, Any]:
        """Get user's current balance"""
        wallet = await self.get_or_create_wallet(user_id)
        return {
            "ok": True,
            "referralBalance": wallet.get("referralBalance", 0),
            "pendingBalance": wallet.get("pendingBalance", 0),
            "totalEarned": wallet.get("totalEarned", 0),
            "totalWithdrawn": wallet.get("totalWithdrawn", 0),
            "availableForWithdrawal": wallet.get("referralBalance", 0),
            "currency": "USD"
        }
    
    async def add_referral_reward(
        self,
        user_id: str,
        amount: float,
        from_user_id: str,
        description: str = ""
    ) -> Dict[str, Any]:
        """Add referral reward to user's wallet"""
        if amount <= 0:
            return {"ok": False, "error": "invalid_amount"}
        
        # Create transaction record
        transaction = {
            "transactionId": f"txn_{secrets.token_hex(8)}",
            "userId": user_id,
            "type": "referral_reward",
            "amount": amount,
            "currency": "USD",
            "fromUserId": from_user_id,
            "description": description,
            "status": "completed",
            "createdAt": datetime.now(timezone.utc)
        }
        
        await self.db.wallet_transactions.insert_one(transaction)
        
        # Update wallet
        result = await self.db.wallets.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "referralBalance": amount,
                    "totalEarned": amount
                },
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            },
            upsert=True
        )
        
        logger.info(f"Wallet: Added ${amount} to {user_id} from {from_user_id}")
        
        return {"ok": True, "amount": amount, "transactionId": transaction["transactionId"]}
    
    async def request_withdrawal(
        self,
        user_id: str,
        amount: float,
        method: str,  # "ton", "usdt_trc20", "stars"
        address: str = None
    ) -> Dict[str, Any]:
        """Request withdrawal of referral earnings"""
        # Get current balance
        wallet = await self.get_or_create_wallet(user_id)
        balance = wallet.get("referralBalance", 0)
        
        # Validate amount
        if amount <= 0:
            return {"ok": False, "error": "invalid_amount"}
        
        if amount < MIN_WITHDRAWAL_USD:
            return {"ok": False, "error": "minimum_not_met", "minimum": MIN_WITHDRAWAL_USD}
        
        if amount > balance:
            return {"ok": False, "error": "insufficient_balance", "balance": balance}
        
        # Check for pending withdrawals
        pending = await self.db.payouts.find_one({
            "userId": user_id,
            "status": "pending"
        })
        
        if pending:
            return {"ok": False, "error": "pending_withdrawal_exists"}
        
        # Calculate fee
        fee = amount * (WITHDRAWAL_FEE_PERCENT / 100)
        net_amount = amount - fee
        
        # Create payout request
        payout = {
            "payoutId": f"payout_{secrets.token_hex(8)}",
            "userId": user_id,
            "amount": amount,
            "fee": fee,
            "netAmount": net_amount,
            "currency": "USD",
            "method": method,
            "address": address,
            "status": "pending",
            "createdAt": datetime.now(timezone.utc),
            "processedAt": None,
            "txHash": None,
            "notes": ""
        }
        
        await self.db.payouts.insert_one(payout)
        
        # Move funds to pending
        await self.db.wallets.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "referralBalance": -amount,
                    "pendingBalance": amount
                },
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )
        
        logger.info(f"Withdrawal requested: {user_id} ${amount} via {method}")
        
        return {
            "ok": True,
            "payoutId": payout["payoutId"],
            "amount": amount,
            "netAmount": net_amount,
            "method": method,
            "status": "pending"
        }
    
    async def get_withdrawal_history(
        self,
        user_id: str,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get user's withdrawal history"""
        payouts = await self.db.payouts.find(
            {"userId": user_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": payouts}
    
    async def get_transactions(
        self,
        user_id: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get user's transaction history"""
        transactions = await self.db.wallet_transactions.find(
            {"userId": user_id},
            {"_id": 0}
        ).sort("createdAt", -1).limit(limit).to_list(limit)
        
        return {"ok": True, "items": transactions}


class PayoutService:
    """Admin payout processing service"""
    
    def __init__(self, db):
        self.db = db
    
    async def get_pending_payouts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all pending payout requests"""
        payouts = await self.db.payouts.find(
            {"status": "pending"},
            {"_id": 0}
        ).sort("createdAt", 1).limit(limit).to_list(limit)
        
        return payouts
    
    async def approve_payout(
        self,
        payout_id: str,
        tx_hash: str = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Approve and process payout"""
        payout = await self.db.payouts.find_one({"payoutId": payout_id})
        
        if not payout:
            return {"ok": False, "error": "payout_not_found"}
        
        if payout["status"] != "pending":
            return {"ok": False, "error": "payout_not_pending"}
        
        user_id = payout["userId"]
        amount = payout["amount"]
        
        # Update payout status
        await self.db.payouts.update_one(
            {"payoutId": payout_id},
            {
                "$set": {
                    "status": "completed",
                    "processedAt": datetime.now(timezone.utc),
                    "txHash": tx_hash,
                    "notes": notes
                }
            }
        )
        
        # Update wallet
        await self.db.wallets.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "pendingBalance": -amount,
                    "totalWithdrawn": amount
                },
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )
        
        # Create transaction record
        transaction = {
            "transactionId": f"txn_{secrets.token_hex(8)}",
            "userId": user_id,
            "type": "withdrawal",
            "amount": -amount,
            "currency": "USD",
            "payoutId": payout_id,
            "txHash": tx_hash,
            "status": "completed",
            "createdAt": datetime.now(timezone.utc)
        }
        await self.db.wallet_transactions.insert_one(transaction)
        
        logger.info(f"Payout approved: {payout_id} ${amount} to {user_id}")
        
        return {"ok": True, "payoutId": payout_id, "amount": amount}
    
    async def reject_payout(
        self,
        payout_id: str,
        reason: str = ""
    ) -> Dict[str, Any]:
        """Reject payout and return funds to user"""
        payout = await self.db.payouts.find_one({"payoutId": payout_id})
        
        if not payout:
            return {"ok": False, "error": "payout_not_found"}
        
        if payout["status"] != "pending":
            return {"ok": False, "error": "payout_not_pending"}
        
        user_id = payout["userId"]
        amount = payout["amount"]
        
        # Update payout status
        await self.db.payouts.update_one(
            {"payoutId": payout_id},
            {
                "$set": {
                    "status": "rejected",
                    "processedAt": datetime.now(timezone.utc),
                    "notes": reason
                }
            }
        )
        
        # Return funds to wallet
        await self.db.wallets.update_one(
            {"userId": user_id},
            {
                "$inc": {
                    "pendingBalance": -amount,
                    "referralBalance": amount
                },
                "$set": {"updatedAt": datetime.now(timezone.utc)}
            }
        )
        
        logger.info(f"Payout rejected: {payout_id} - {reason}")
        
        return {"ok": True, "payoutId": payout_id, "refunded": amount}
    
    async def get_payout_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get payout statistics for admin dashboard"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Total paid out
        total_pipeline = [
            {"$match": {"status": "completed", "processedAt": {"$gte": cutoff}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
        ]
        total_result = await self.db.payouts.aggregate(total_pipeline).to_list(1)
        
        # Pending payouts
        pending_pipeline = [
            {"$match": {"status": "pending"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}}
        ]
        pending_result = await self.db.payouts.aggregate(pending_pipeline).to_list(1)
        
        return {
            "ok": True,
            "totalPaidOut": total_result[0]["total"] if total_result else 0,
            "payoutCount": total_result[0]["count"] if total_result else 0,
            "pendingAmount": pending_result[0]["total"] if pending_result else 0,
            "pendingCount": pending_result[0]["count"] if pending_result else 0,
            "days": days
        }


async def ensure_wallet_indexes(db):
    """Create indexes for wallet collections"""
    # wallets
    await db.wallets.create_index("userId", unique=True)
    
    # wallet_transactions
    await db.wallet_transactions.create_index("transactionId", unique=True)
    await db.wallet_transactions.create_index("userId")
    await db.wallet_transactions.create_index([("createdAt", -1)])
    
    # payouts
    await db.payouts.create_index("payoutId", unique=True)
    await db.payouts.create_index("userId")
    await db.payouts.create_index("status")
    await db.payouts.create_index([("createdAt", -1)])
    
    logger.info("Wallet indexes created")
