"""
Referral Bot Commands
Bot handlers for /referrals, /withdraw, /subscribe commands
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import httpx

from .referral_service import ReferralService, REFERRAL_REWARD_USD
from .wallet_service import WalletService, MIN_WITHDRAWAL_USD
from .subscription_service import SubscriptionService, PaymentService, SUBSCRIPTION_PRICE_STARS

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("TG_BOT_USERNAME", "ARKHOR_bot")


async def send_message(chat_id: int, text: str, reply_markup: dict = None, parse_mode: str = "Markdown"):
    """Send message via Telegram API"""
    if not BOT_TOKEN:
        return {"ok": False, "error": "BOT_TOKEN not set"}
    
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            if reply_markup:
                payload["reply_markup"] = reply_markup
            
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
                timeout=10.0
            )
            return response.json()
    except Exception as e:
        logger.error(f"Send message error: {e}")
        return {"ok": False, "error": str(e)}


async def handle_referrals_command(db, chat_id: int, user_id: str) -> Dict[str, Any]:
    """
    Handle /referrals command
    Shows referral stats, link, and earnings
    """
    referral_svc = ReferralService(db)
    stats = await referral_svc.get_user_referral_stats(user_id)
    
    if not stats.get("ok"):
        await send_message(chat_id, "❌ Помилка отримання даних")
        return {"ok": False}
    
    # Format balance
    balance = stats.get("balance", 0)
    monthly = stats.get("monthlyIncome", 0)
    total_earned = stats.get("totalEarned", 0)
    total_referrals = stats.get("totalReferrals", 0)
    active_referrals = stats.get("activeReferrals", 0)
    ref_link = stats.get("referralLink", "")
    
    text = f"""💰 *Реферальна програма*

*Ваш баланс:* ${balance:.2f}

📊 *Статистика:*
👥 Запрошено: {total_referrals}
✅ Активних: {active_referrals}
💵 Дохід/місяць: ${monthly:.2f}
📈 Всього зароблено: ${total_earned:.2f}

*Ваше посилання:*
`{ref_link}`

━━━━━━━━━━━━━━━━━━━━

💡 *Як це працює:*
• Запрошуй друзів за посиланням
• Коли друг оплачує підписку — ти отримуєш *${REFERRAL_REWARD_USD:.2f}*
• Дохід нараховується *щомісяця* поки друг платить

🏆 Мінімум для виводу: *${MIN_WITHDRAWAL_USD:.0f}*"""
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📤 Поділитися", "switch_inline_query": f"Приєднуйся до RADAR! {ref_link}"},
            ],
            [
                {"text": "💸 Вивести", "callback_data": "ref_withdraw"},
                {"text": "🏆 Топ", "callback_data": "ref_leaderboard"}
            ],
            [
                {"text": "📜 Історія", "callback_data": "ref_history"}
            ]
        ]
    }
    
    await send_message(chat_id, text, keyboard)
    
    return {"ok": True, "action": "referrals"}


async def handle_withdraw_command(db, chat_id: int, user_id: str) -> Dict[str, Any]:
    """
    Handle /withdraw command
    Shows withdrawal options
    """
    wallet_svc = WalletService(db)
    balance = await wallet_svc.get_balance(user_id)
    
    available = balance.get("referralBalance", 0)
    
    if available < MIN_WITHDRAWAL_USD:
        text = f"""💸 *Виведення коштів*

Ваш баланс: *${available:.2f}*

⚠️ Мінімальна сума для виведення: *${MIN_WITHDRAWAL_USD:.0f}*

Запросіть ще {int((MIN_WITHDRAWAL_USD - available) / REFERRAL_REWARD_USD) + 1} друзів, щоб досягти мінімуму!"""
        
        await send_message(chat_id, text)
        return {"ok": True, "action": "withdraw_minimum"}
    
    text = f"""💸 *Виведення коштів*

Доступно для виведення: *${available:.2f}*

Оберіть спосіб виведення:"""
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "💎 TON (Toncoin)", "callback_data": f"withdraw_ton:{available}"}],
            [{"text": "💵 USDT (TRC-20)", "callback_data": f"withdraw_usdt:{available}"}],
            [{"text": "⭐ Telegram Stars", "callback_data": f"withdraw_stars:{available}"}],
            [{"text": "❌ Скасувати", "callback_data": "cancel"}]
        ]
    }
    
    await send_message(chat_id, text, keyboard)
    
    return {"ok": True, "action": "withdraw_options"}


async def handle_withdraw_callback(
    db, 
    chat_id: int, 
    message_id: int,
    user_id: str, 
    method: str, 
    amount: float
) -> Dict[str, Any]:
    """Handle withdrawal method selection"""
    
    if method in ["ton", "usdt"]:
        # Ask for wallet address
        text = f"""💸 *Виведення ${amount:.2f} на {method.upper()}*

Надішліть адресу вашого гаманця:"""
        
        # Store pending withdrawal state
        await db.user_states.update_one(
            {"userId": user_id},
            {
                "$set": {
                    "state": "awaiting_wallet_address",
                    "withdrawMethod": method,
                    "withdrawAmount": amount,
                    "updatedAt": datetime.now(timezone.utc)
                }
            },
            upsert=True
        )
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "❌ Скасувати", "callback_data": "cancel_withdraw"}]
            ]
        }
        
        await send_message(chat_id, text, keyboard)
        return {"ok": True, "action": "awaiting_address"}
    
    elif method == "stars":
        # Process Stars withdrawal immediately
        wallet_svc = WalletService(db)
        result = await wallet_svc.request_withdrawal(
            user_id=user_id,
            amount=amount,
            method="stars",
            address=None
        )
        
        if result.get("ok"):
            text = f"""✅ *Заявка на виведення створена*

Сума: *${amount:.2f}*
Спосіб: Telegram Stars

Заявку буде оброблено протягом 24 годин."""
        else:
            text = f"❌ Помилка: {result.get('error', 'Unknown')}"
        
        await send_message(chat_id, text)
        return result
    
    return {"ok": False, "error": "unknown_method"}


async def handle_wallet_address(
    db,
    chat_id: int,
    user_id: str,
    address: str
) -> Dict[str, Any]:
    """Handle wallet address input for withdrawal"""
    
    # Get pending state
    state = await db.user_states.find_one({"userId": user_id})
    
    if not state or state.get("state") != "awaiting_wallet_address":
        return {"ok": False, "error": "no_pending_withdrawal"}
    
    method = state.get("withdrawMethod")
    amount = state.get("withdrawAmount", 0)
    
    # Validate address format (basic check)
    if method == "ton" and not (address.startswith("EQ") or address.startswith("UQ")):
        await send_message(chat_id, "❌ Невірний формат TON адреси. Спробуйте ще раз.")
        return {"ok": False, "error": "invalid_ton_address"}
    
    if method == "usdt" and not address.startswith("T"):
        await send_message(chat_id, "❌ Невірний формат TRC-20 адреси. Спробуйте ще раз.")
        return {"ok": False, "error": "invalid_usdt_address"}
    
    # Create withdrawal request
    wallet_svc = WalletService(db)
    result = await wallet_svc.request_withdrawal(
        user_id=user_id,
        amount=amount,
        method=method,
        address=address
    )
    
    # Clear state
    await db.user_states.delete_one({"userId": user_id})
    
    if result.get("ok"):
        text = f"""✅ *Заявка на виведення створена*

Сума: *${amount:.2f}*
Спосіб: {method.upper()}
Адреса: `{address}`

Заявку буде оброблено протягом 24 годин.
ID заявки: `{result.get('payoutId')}`"""
    else:
        text = f"❌ Помилка: {result.get('error', 'Unknown')}"
    
    await send_message(chat_id, text)
    return result


async def handle_subscribe_command(db, chat_id: int, user_id: str) -> Dict[str, Any]:
    """
    Handle /subscribe command
    Shows subscription info and payment button
    """
    sub_svc = SubscriptionService(db)
    is_subscribed = await sub_svc.is_subscribed(user_id)
    
    if is_subscribed:
        sub = await sub_svc.get_subscription(user_id)
        expires = sub.get("expiresAt", "")
        if isinstance(expires, datetime):
            expires_str = expires.strftime("%d.%m.%Y")
        else:
            expires_str = str(expires)[:10]
        
        text = f"""✅ *У вас активна підписка*

📅 Дійсна до: *{expires_str}*

Дякуємо за підтримку! 🙏"""
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "🔄 Продовжити підписку", "callback_data": "subscribe_extend"}]
            ]
        }
    else:
        text = f"""⭐ *RADAR Premium*

Отримайте повний доступ до всіх функцій:
• 📡 Необмежені сповіщення
• 🎯 Розширений радіус
• 🏆 Пріоритетна підтримка
• 💰 Реферальна програма

💵 *Ціна: {SUBSCRIPTION_PRICE_STARS} Stars (~$1/міс)*"""
        
        keyboard = {
            "inline_keyboard": [
                [{"text": f"⭐ Оплатити {SUBSCRIPTION_PRICE_STARS} Stars", "callback_data": "subscribe_pay"}]
            ]
        }
    
    await send_message(chat_id, text, keyboard)
    
    return {"ok": True, "action": "subscribe", "isSubscribed": is_subscribed}


async def handle_subscribe_callback(db, chat_id: int, user_id: str) -> Dict[str, Any]:
    """Handle subscribe button - create invoice"""
    payment_svc = PaymentService(db)
    result = await payment_svc.create_invoice(chat_id, user_id)
    
    if not result.get("ok"):
        await send_message(chat_id, f"❌ Помилка створення рахунку: {result.get('error')}")
    
    return result


async def handle_referral_leaderboard(db, chat_id: int) -> Dict[str, Any]:
    """Show top referrers leaderboard"""
    referral_svc = ReferralService(db)
    leaders = await referral_svc.get_referral_leaderboard(limit=10)
    
    if not leaders:
        text = "🏆 *Рейтинг рефералів*\n\nПоки що пусто. Будьте першим!"
    else:
        lines = ["🏆 *Топ-10 рефералів*", ""]
        
        medals = ["🥇", "🥈", "🥉"]
        for i, leader in enumerate(leaders):
            medal = medals[i] if i < 3 else f"{i+1}."
            earned = leader.get("totalEarned", 0)
            referrals = leader.get("referralCount", 0)
            lines.append(f"{medal} ${earned:.2f} — {referrals} запрошених")
        
        text = "\n".join(lines)
    
    await send_message(chat_id, text)
    
    return {"ok": True, "action": "leaderboard"}


async def handle_referral_history(db, chat_id: int, user_id: str) -> Dict[str, Any]:
    """Show user's referral history"""
    referral_svc = ReferralService(db)
    result = await referral_svc.get_user_referrals(user_id, limit=10)
    
    referrals = result.get("items", [])
    
    if not referrals:
        text = "📜 *Історія рефералів*\n\nПоки що нікого не запросили."
    else:
        lines = ["📜 *Останні реферали*", ""]
        
        for ref in referrals:
            status = "✅" if ref.get("status") == "active" else "⏳"
            username = ref.get("referredUsername", "Анонім")
            earned = ref.get("rewardPaid", 0)
            payments = ref.get("paymentCount", 0)
            
            lines.append(f"{status} @{username} — ${earned:.2f} ({payments} платежів)")
        
        text = "\n".join(lines)
    
    await send_message(chat_id, text)
    
    return {"ok": True, "action": "history"}


async def process_start_referral(db, user_id: str, start_param: str, username: str = None) -> Dict[str, Any]:
    """
    Process /start with referral code
    Called when user starts bot with ?start=ref_XXXX
    """
    if not start_param.startswith("ref_"):
        return {"ok": False, "error": "not_referral"}
    
    referral_svc = ReferralService(db)
    result = await referral_svc.register_referral(
        new_user_id=user_id,
        referral_code=start_param,
        username=username
    )
    
    if result.get("ok"):
        logger.info(f"Referral registered: {user_id} via {start_param}")
    
    return result


# Initialize indexes on module load
async def ensure_referral_bot_indexes(db):
    """Ensure all referral-related indexes exist"""
    from .referral_service import ensure_referral_indexes
    from .wallet_service import ensure_wallet_indexes
    from .subscription_service import ensure_payment_indexes
    
    await ensure_referral_indexes(db)
    await ensure_wallet_indexes(db)
    await ensure_payment_indexes(db)
    
    # User states for withdrawal flow
    await db.user_states.create_index("userId", unique=True)
    
    logger.info("Referral bot indexes initialized")
