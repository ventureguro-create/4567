"""
Bot Keyboard Builder - New Clean UX
Main menu: 3 buttons only
➕ Повідомити | 📡 Радар | 👤 Профіль
"""
from typing import List, Dict, Any, Optional

# Report types - 4 main signals
REPORT_TYPES = [
    {"type": "virus", "emoji": "🦠"},
    {"type": "trash", "emoji": "🗑"},
    {"type": "rain", "emoji": "🌧"},
    {"type": "police", "emoji": "🚔"}
]

# Event type icons
EVENT_ICONS = {t["type"]: t["emoji"] for t in REPORT_TYPES}
EVENT_LABELS = {t["type"]: t["emoji"] for t in REPORT_TYPES}


class BotKeyboardBuilder:
    """Builder for Telegram keyboards - Clean 3-button UI"""
    
    @staticmethod
    def main_menu() -> Dict[str, Any]:
        """
        Main menu - 3 primary buttons
        ➕ Повідомити - main action
        📡 Радар - status & control
        👤 Профіль - all user stuff
        """
        return {
            "keyboard": [
                ["➕ Повідомити"],
                ["📡 Радар", "👤 Профіль"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": False
        }
    
    @staticmethod
    def report_types() -> Dict[str, Any]:
        """
        Signal type selection - 4 emoji buttons in one row
        🦠 🗑 🌧 🚔
        """
        buttons = [[]]
        for rt in REPORT_TYPES:
            buttons[0].append({
                "text": rt['emoji'],
                "callback_data": f"report_type:{rt['type']}"
            })
        
        # Cancel row
        buttons.append([{"text": "❌ Скасувати", "callback_data": "cancel"}])
        
        return {"inline_keyboard": buttons}
    
    @staticmethod
    def location_request() -> Dict[str, Any]:
        """Location request with privacy note"""
        return {
            "keyboard": [
                [{"text": "📍 Надіслати локацію", "request_location": True}],
                ["↩️ Назад"]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }
    
    @staticmethod
    def photo_option() -> Dict[str, Any]:
        """Photo add/skip choice"""
        return {
            "inline_keyboard": [
                [
                    {"text": "📷 Додати фото", "callback_data": "report_photo:add"},
                    {"text": "➡️ Без фото", "callback_data": "report_photo:skip"}
                ]
            ]
        }
    
    @staticmethod
    def confirmation_buttons(report_id: str) -> Dict[str, Any]:
        """
        Nearby signal confirmation - simple yes/no
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "✔ Так", "callback_data": f"confirm:{report_id}:confirm"},
                    {"text": "✖ Ні", "callback_data": f"confirm:{report_id}:reject"}
                ]
            ]
        }
    
    @staticmethod
    def radar_menu(is_enabled: bool, radius: int = 1000, ttl_label: str = "15 хв") -> Dict[str, Any]:
        """
        📡 Радар screen
        Shows current status with action buttons
        """
        toggle_text = "🔴 Вимкнути" if is_enabled else "🟢 Увімкнути"
        toggle_cb = "radar_off" if is_enabled else "radar_on"
        
        buttons = [
            [{"text": toggle_text, "callback_data": toggle_cb}]
        ]
        
        if is_enabled:
            buttons.extend([
                [{"text": "📍 Оновити локацію", "callback_data": "menu_location"}],
                [
                    {"text": "📏 Радіус", "callback_data": "menu_radius"},
                    {"text": "🧩 Типи сигналів", "callback_data": "menu_types"}
                ]
            ])
        
        return {"inline_keyboard": buttons}
    
    @staticmethod
    def profile_menu() -> Dict[str, Any]:
        """
        👤 Профіль screen buttons
        Заробіток + Підписка в одному рядку, Налаштування знизу
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "💰 Заробіток", "callback_data": "menu_earnings"},
                    {"text": "⭐ Підписка", "callback_data": "menu_subscribe"}
                ],
                [{"text": "⚙️ Налаштування", "callback_data": "menu_settings"}]
            ]
        }
    
    @staticmethod
    def settings_menu() -> Dict[str, Any]:
        """
        ⚙️ Налаштування screen
        Компактна група: 
        - Локація + Радіус
        - Типи сигналів + Тихі години
        - Допомога
        - Назад
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "📍 Локація", "callback_data": "menu_location_settings"},
                    {"text": "📏 Радіус", "callback_data": "menu_radius"}
                ],
                [
                    {"text": "🧩 Типи сигналів", "callback_data": "menu_types"},
                    {"text": "🌙 Тихі години", "callback_data": "menu_quiet"}
                ],
                [{"text": "❓ Допомога", "callback_data": "menu_help"}],
                [{"text": "↩️ Назад", "callback_data": "back_profile"}]
            ]
        }
    
    @staticmethod
    def earnings_menu(balance: float = 0, referrals_count: int = 0) -> Dict[str, Any]:
        """
        💰 Заробіток screen buttons
        """
        return {
            "inline_keyboard": [
                [{"text": "👥 Запросити друзів", "callback_data": "share_referral"}],
                [{"text": "💸 Вивести", "callback_data": "ref_withdraw"}],
                [{"text": "↩️ Назад", "callback_data": "back_profile"}]
            ]
        }
    
    @staticmethod
    def subscription_menu(is_active: bool = False) -> Dict[str, Any]:
        """
        ⭐ Підписка screen buttons
        """
        if is_active:
            return {
                "inline_keyboard": [
                    [{"text": "Продовжити", "callback_data": "subscribe_extend"}],
                    [{"text": "↩️ Назад", "callback_data": "back_profile"}]
                ]
            }
        else:
            return {
                "inline_keyboard": [
                    [{"text": "⭐ Оформити підписку", "callback_data": "subscribe_pay"}],
                    [{"text": "↩️ Назад", "callback_data": "back_profile"}]
                ]
            }
    
    @staticmethod
    def location_ttl_options(current_mode: str = "15m") -> Dict[str, Any]:
        """
        Location TTL selection - privacy-first
        """
        modes = [
            ("5m", "5 хв"),
            ("15m", "15 хв ⭐"),
            ("1h", "1 година"),
            ("1d", "1 день"),
        ]
        
        buttons = []
        row = []
        
        for mode, label in modes:
            mark = "✅ " if mode == current_mode else ""
            row.append({"text": f"{mark}{label}", "callback_data": f"location_ttl:{mode}"})
            
            if len(row) == 2:
                buttons.append(row)
                row = []
        
        if row:
            buttons.append(row)
        
        buttons.append([{"text": "↩️ Назад", "callback_data": "menu_settings"}])
        
        return {"inline_keyboard": buttons}
    
    @staticmethod
    def session_expiring(remaining_minutes: int) -> Dict[str, Any]:
        """
        Session about to expire notification
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "+15 хв", "callback_data": "extend_session:15"},
                    {"text": "+1 година", "callback_data": "extend_session:60"}
                ],
                [{"text": "🚫 Вимкнути радар", "callback_data": "session_disable"}]
            ]
        }
    
    @staticmethod
    def radius_options(current_radius: int = 1000) -> Dict[str, Any]:
        """Radius selection"""
        options = [500, 1000, 2000, 3000]
        buttons = []
        for r in options:
            label = f"{'✅ ' if r == current_radius else ''}{r}м"
            buttons.append({"text": label, "callback_data": f"radius_{r}"})
        
        return {
            "inline_keyboard": [
                buttons[:2], 
                buttons[2:],
                [{"text": "↩️ Назад", "callback_data": "back_radar"}]
            ]
        }
    
    @staticmethod
    def event_types(enabled_types: List[str]) -> Dict[str, Any]:
        """Event type toggles"""
        row = []
        for rt in REPORT_TYPES:
            is_on = rt["type"] in enabled_types
            status = "✅" if is_on else ""
            row.append({
                "text": f"{status}{rt['emoji']}",
                "callback_data": f"type_{rt['type']}"
            })
        
        return {
            "inline_keyboard": [
                row, 
                [{"text": "↩️ Назад", "callback_data": "back_radar"}]
            ]
        }
    
    @staticmethod
    def quiet_hours_toggle(is_enabled: bool) -> Dict[str, Any]:
        """Quiet hours toggle"""
        text = "🔕 Вимкнути" if is_enabled else "🔔 Увімкнути"
        callback = "quiet_off" if is_enabled else "quiet_on"
        
        return {
            "inline_keyboard": [
                [{"text": f"{text} (23:00-07:00)", "callback_data": callback}],
                [{"text": "↩️ Назад", "callback_data": "menu_settings"}]
            ]
        }
    
    @staticmethod
    def withdraw_methods(balance: float) -> Dict[str, Any]:
        """Withdrawal method selection"""
        return {
            "inline_keyboard": [
                [{"text": "💎 TON", "callback_data": f"withdraw_ton:{balance}"}],
                [{"text": "💵 USDT (TRC-20)", "callback_data": f"withdraw_usdt:{balance}"}],
                [{"text": "⭐ Telegram Stars", "callback_data": f"withdraw_stars:{balance}"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel_withdraw"}]
            ]
        }
    
    @staticmethod
    def back_button(callback: str = "menu_back") -> Dict[str, Any]:
        """Simple back button"""
        return {
            "inline_keyboard": [[{"text": "↩️ Назад", "callback_data": callback}]]
        }
    
    @staticmethod
    def remove_keyboard() -> Dict[str, Any]:
        """Remove custom keyboard"""
        return {"remove_keyboard": True}
    
    # Legacy compatibility
    @staticmethod
    def extended_menu() -> Dict[str, Any]:
        """Alias for settings_menu"""
        return BotKeyboardBuilder.settings_menu()
    
    @staticmethod
    def report_event_types() -> Dict[str, Any]:
        """Alias for report_types"""
        return BotKeyboardBuilder.report_types()
    
    @staticmethod
    def radar_toggle(is_enabled: bool) -> Dict[str, Any]:
        """Legacy radar toggle"""
        return BotKeyboardBuilder.radar_menu(is_enabled)
    
    @staticmethod
    def sensitivity_options(current: str = "medium") -> Dict[str, Any]:
        """Sensitivity selection"""
        options = [("low", "🔇 Низька"), ("medium", "🔉 Середня"), ("high", "🔊 Висока")]
        buttons = []
        for val, label in options:
            mark = "✅ " if val == current else ""
            buttons.append({"text": f"{mark}{label}", "callback_data": f"sens_{val}"})
        return {"inline_keyboard": [buttons]}
    
    @staticmethod
    def confirm_event(event_id: str) -> Dict[str, Any]:
        """Legacy confirm event"""
        return BotKeyboardBuilder.confirmation_buttons(event_id)
    
    @staticmethod
    def mute_options() -> Dict[str, Any]:
        """Mute duration options"""
        return {
            "inline_keyboard": [
                [
                    {"text": "1 год", "callback_data": "mute_1h"},
                    {"text": "6 год", "callback_data": "mute_6h"},
                    {"text": "24 год", "callback_data": "mute_24h"}
                ],
                [{"text": "↩️ Назад", "callback_data": "menu_back"}]
            ]
        }


    # ==================== Location Mode Selection ====================
    
    @staticmethod
    def location_mode_selection() -> Dict[str, Any]:
        """
        Choose location input mode for creating event:
        📍 My location - Quick, 1 tap
        🗺 Pick on map - Open WebApp map picker
        """
        return {
            "inline_keyboard": [
                [{"text": "📍 Використати мою локацію", "callback_data": "location_mode:current"}],
                [{"text": "🗺 Вказати на карті", "callback_data": "location_mode:map"}],
                [{"text": "❌ Скасувати", "callback_data": "cancel"}]
            ]
        }
    
    @staticmethod
    def quick_signal_buttons() -> Dict[str, Any]:
        """
        Quick signal buttons - 1 tap to send
        🗑 Сміття поруч | 🦠 Вірус | etc
        """
        return {
            "inline_keyboard": [
                [
                    {"text": "🗑 Сміття", "callback_data": "quick_signal:trash"},
                    {"text": "🦠 Вірус", "callback_data": "quick_signal:virus"}
                ],
                [
                    {"text": "🌧 Дощ", "callback_data": "quick_signal:rain"},
                    {"text": "🚔 Поліція", "callback_data": "quick_signal:police"}
                ],
                [{"text": "✏️ Детальніше...", "callback_data": "report_detailed"}]
            ]
        }
    
    # ==================== Tier/Subscription ====================
    
    @staticmethod
    def tier_upgrade_prompt(current_tier: str = "FREE") -> Dict[str, Any]:
        """Prompt user to upgrade tier"""
        return {
            "inline_keyboard": [
                [{"text": "⭐ Оформити PRO", "callback_data": "subscribe_monthly"}],
                [{"text": "↩️ Пізніше", "callback_data": "menu_back"}]
            ]
        }
    
    @staticmethod
    def trial_welcome() -> Dict[str, Any]:
        """Welcome message for new trial users"""
        return {
            "inline_keyboard": [
                [{"text": "🎉 Почати", "callback_data": "trial_start"}],
                [{"text": "ℹ️ Що входить?", "callback_data": "trial_info"}]
            ]
        }
    
    # ==================== Admin Panel ====================
    
    @staticmethod
    def admin_panel() -> Dict[str, Any]:
        """Admin panel keyboard"""
        return {
            "inline_keyboard": [
                [{"text": "📩 Черга модерації", "callback_data": "admin_queue"}],
                [{"text": "📊 Статистика", "callback_data": "admin_stats"}],
                [{"text": "👥 Користувачі", "callback_data": "admin_users"}],
                [{"text": "↩️ Назад", "callback_data": "menu_back"}]
            ]
        }
    
    @staticmethod
    def admin_moderation(signal_id: str) -> Dict[str, Any]:
        """Moderation buttons for pending signals"""
        return {
            "inline_keyboard": [
                [
                    {"text": "✔ Підтвердити", "callback_data": f"admin_approve:{signal_id}"},
                    {"text": "❌ Відхилити", "callback_data": f"admin_reject:{signal_id}"}
                ],
                [
                    {"text": "🚫 Забанити", "callback_data": f"admin_ban:{signal_id}"},
                    {"text": "⏭ Пропустити", "callback_data": "admin_skip"}
                ]
            ]
        }
