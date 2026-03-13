/**
 * Profile Page - Modern Stats & Settings
 * Glass cards, progress bars, clean layout
 */
import { useEffect, useState } from 'react';
import { 
  User, Star, Trophy, Share2, Settings, ChevronRight, 
  Zap, Target, CheckCircle, Loader2, Gift, Crown,
  Shield, TrendingUp, Flame, Send
} from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { getTelegramUser, vibrate, isTelegramWebApp } from '../lib/telegram';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';
const CHANNEL_USERNAME = 'ARKHOR';
const CHANNEL_URL = 'https://t.me/ARKHOR';

// ANONYMOUS Leaderboard Section
function LeaderboardSection({ onBack }) {
  const [leaders, setLeaders] = useState([]);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchLeaderboard = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/geo/leaderboard?limit=10`);
        const data = await res.json();
        if (data.ok && data.items && data.items.length > 0) {
          // Make all users anonymous
          const anonymousLeaders = data.items.map((item, index) => ({
            rank: index + 1,
            name: 'Анонім',
            signals: item.totalReports || item.reports || 0,
            badge: index === 0 ? '👑' : index === 1 ? '🥈' : index === 2 ? '🥉' : null
          }));
          setLeaders(anonymousLeaders);
        } else {
          // Fallback data when no real data
          setLeaders([
            { rank: 1, name: 'Анонім', signals: 156, badge: '👑' },
            { rank: 2, name: 'Анонім', signals: 134, badge: '🥈' },
            { rank: 3, name: 'Анонім', signals: 98, badge: '🥉' },
            { rank: 4, name: 'Анонім', signals: 87, badge: null },
            { rank: 5, name: 'Анонім', signals: 76, badge: null },
          ]);
        }
      } catch (err) {
        console.error('Failed to fetch leaderboard:', err);
        // Fallback
        setLeaders([
          { rank: 1, name: 'Анонім', signals: 156, badge: '👑' },
          { rank: 2, name: 'Анонім', signals: 134, badge: '🥈' },
          { rank: 3, name: 'Анонім', signals: 98, badge: '🥉' },
        ]);
      } finally {
        setLoading(false);
      }
    };
    
    fetchLeaderboard();
  }, []);
  
  return (
    <div className="h-full flex flex-col bg-background pb-[80px]" data-testid="leaderboard-section">
      <div className="flex items-center gap-3 p-4 bg-surface">
        <button 
          onClick={onBack}
          className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-neutral-100 active:scale-95 transition-all"
        >
          <ChevronRight className="rotate-180" size={24} />
        </button>
        <h2 className="text-lg font-semibold text-neutral-900">Рейтинг</h2>
      </div>
      
      <div className="flex-1 p-4">
        <div className="text-center mb-6">
          <div className="w-16 h-16 bg-warning/10 rounded-full flex items-center justify-center mx-auto mb-3">
            <Trophy size={32} className="text-warning" />
          </div>
          <p className="text-sm text-neutral-500">Всі учасники анонімні</p>
        </div>
        
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={24} className="animate-spin text-primary" />
          </div>
        ) : (
          <div className="space-y-2">
            {leaders.map((leader) => (
              <div 
                key={leader.rank}
                className="glass-card-solid p-4 flex items-center gap-4"
              >
                <div className="w-8 h-8 bg-neutral-100 rounded-full flex items-center justify-center font-bold text-neutral-600">
                  {leader.badge || leader.rank}
                </div>
                <div className="flex-1">
                  <span className="font-medium text-neutral-900">{leader.name}</span>
                </div>
                <span className="text-sm text-neutral-500">{leader.signals}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { telegramUser, user, fetchProfile, radarActive, radarRadius } = useAppStore();
  const [activeSection, setActiveSection] = useState(null);
  const [subscription, setSubscription] = useState(null);
  const [loadingSubscription, setLoadingSubscription] = useState(false);
  const [streak, setStreak] = useState(0);
  const [channelSubscribed, setChannelSubscribed] = useState(false);
  const [loadingChannel, setLoadingChannel] = useState(false);
  const [privacySettings, setPrivacySettings] = useState({
    locationRetention: '1h',
    locationPrecision: 'exact'
  });
  
  useEffect(() => {
    fetchProfile();
    fetchSubscription();
    checkChannelSubscription();
    fetchPrivacySettings();
    // Calculate streak from user data
    if (user?.streak) {
      setStreak(user.streak);
    }
  }, [fetchProfile, user]);
  
  // Fetch privacy settings
  const fetchPrivacySettings = async () => {
    const userId = telegramUser?.id || getTelegramUser()?.id;
    if (!userId) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/user/${userId}/settings`);
      const data = await res.json();
      if (data.ok && data.settings) {
        setPrivacySettings({
          locationRetention: data.settings.locationRetention || '1h',
          locationPrecision: data.settings.locationPrecision || 'exact'
        });
      }
    } catch (err) {
      console.error('Failed to fetch privacy settings:', err);
    }
  };
  
  // Update privacy settings
  const updatePrivacySettings = async (key, value) => {
    vibrate('light');
    const newSettings = { ...privacySettings, [key]: value };
    setPrivacySettings(newSettings);
    
    const userId = telegramUser?.id || getTelegramUser()?.id;
    if (!userId) return;
    
    try {
      await fetch(`${API_BASE}/api/geo/miniapp/user/${userId}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSettings)
      });
    } catch (err) {
      console.error('Failed to save privacy settings:', err);
    }
  };
  
  // Check if user is subscribed to Telegram channel
  const checkChannelSubscription = async () => {
    const userId = telegramUser?.id || getTelegramUser()?.id;
    if (!userId) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/channel/check?userId=${userId}&channel=${CHANNEL_USERNAME}`);
      const data = await res.json();
      if (data.ok) {
        setChannelSubscribed(data.isMember);
      }
    } catch (err) {
      console.error('Failed to check channel subscription:', err);
    }
  };
  
  // Open channel and then re-check subscription
  const handleOpenChannel = async () => {
    vibrate('medium');
    
    // Open channel in Telegram
    if (isTelegramWebApp() && window.Telegram?.WebApp?.openTelegramLink) {
      window.Telegram.WebApp.openTelegramLink(CHANNEL_URL);
    } else {
      window.open(CHANNEL_URL, '_blank');
    }
    
    // Re-check subscription after a delay (user might subscribe)
    setLoadingChannel(true);
    setTimeout(async () => {
      await checkChannelSubscription();
      setLoadingChannel(false);
    }, 3000);
  };
  
  const fetchSubscription = async () => {
    const userId = telegramUser?.id || getTelegramUser()?.id;
    if (!userId) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/subscription/status?userId=${userId}`);
      const data = await res.json();
      if (data.ok) {
        setSubscription(data);
      }
    } catch (err) {
      console.error('Failed to fetch subscription:', err);
    }
  };
  
  const handleSubscribe = async () => {
    vibrate('medium');
    setLoadingSubscription(true);
    
    try {
      if (isTelegramWebApp() && window.Telegram?.WebApp) {
        const userId = telegramUser?.id || getTelegramUser()?.id;
        
        const res = await fetch(`${API_BASE}/api/geo/miniapp/subscription/create-invoice`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ userId, chatId: userId })
        });
        
        const data = await res.json();
        
        if (data.ok) {
          alert('Перевірте повідомлення від бота для оплати');
        } else {
          alert(data.error || 'Помилка створення рахунку');
        }
      } else {
        alert('Для оплати через Telegram Stars відкрийте бота');
      }
    } catch (err) {
      console.error('Subscribe error:', err);
      alert('Помилка оплати');
    } finally {
      setLoadingSubscription(false);
    }
  };
  
  const displayUser = telegramUser || getTelegramUser() || { 
    firstName: 'User',
    username: 'anonymous'
  };
  
  const stats = user || {
    signalsSent: 0,
    signalsConfirmed: 0,
    trustScore: 50,
    level: 1,
    xp: 0,
    xpNext: 100,
  };
  
  const xpProgress = stats.xp ? (stats.xp / stats.xpNext) * 100 : 0;
  
  const openSection = (section) => {
    vibrate('light');
    setActiveSection(section);
  };
  
  const shareReferral = async () => {
    vibrate('medium');
    const userId = telegramUser?.id || getTelegramUser()?.id || 'user';
    const referralLink = `https://t.me/ARKHOR_bot?startapp=ref_${userId}`;
    
    try {
      // Try Telegram WebApp share first
      if (isTelegramWebApp() && window.Telegram?.WebApp?.openTelegramLink) {
        const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(referralLink)}&text=${encodeURIComponent('Приєднуйся до Radar! Слідкуй за сигналами у місті!')}`;
        window.Telegram.WebApp.openTelegramLink(shareUrl);
        return;
      }
      
      // Try native share
      if (navigator.share) {
        await navigator.share({
          title: 'Приєднуйся до Radar',
          text: 'Слідкуй за сигналами у місті!',
          url: referralLink
        });
        return;
      }
      
      // Fallback to clipboard
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(referralLink);
        alert('Посилання скопійовано!');
      } else {
        // Last resort - show link in alert
        alert(`Ваше реферальне посилання:\n${referralLink}`);
      }
    } catch (err) {
      console.error('Share error:', err);
      // Show link if all else fails
      alert(`Ваше реферальне посилання:\n${referralLink}`);
    }
  };
  
  // Section: Referrals
  if (activeSection === 'referrals') {
    return (
      <div className="h-full flex flex-col bg-background pb-[80px]" data-testid="referrals-section">
        <div className="flex items-center gap-3 p-4 bg-surface">
          <button 
            onClick={() => setActiveSection(null)}
            className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-neutral-100 active:scale-95 transition-all"
          >
            <ChevronRight className="rotate-180" size={24} />
          </button>
          <h2 className="text-lg font-semibold text-neutral-900">Реферали</h2>
        </div>
        
        <div className="flex-1 p-4">
          <div className="text-center mb-8">
            <div className="w-20 h-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <Gift size={40} className="text-primary" />
            </div>
            <h3 className="text-xl font-bold text-neutral-900 mb-2">Запрошуй друзів</h3>
            <p className="text-neutral-500">Отримуй бонуси за кожного друга</p>
          </div>
          
          <div className="grid grid-cols-3 gap-3 mb-6">
            {[
              { value: '0', label: 'Запрошено' },
              { value: '0', label: 'Активних' },
              { value: '$0', label: 'Зароблено' },
            ].map((item, i) => (
              <div key={i} className="glass-card-solid p-4 text-center">
                <div className="text-2xl font-bold text-neutral-900">{item.value}</div>
                <div className="text-xs text-neutral-500 mt-1">{item.label}</div>
              </div>
            ))}
          </div>
          
          <button 
            onClick={shareReferral}
            className="w-full py-4 bg-primary text-white rounded-2xl font-semibold flex items-center justify-center gap-3 shadow-lg shadow-primary/20 active:scale-[0.98] transition-transform"
          >
            <Share2 size={20} />
            Поділитись посиланням
          </button>
        </div>
      </div>
    );
  }
  
  // Section: Leaderboard - ANONYMOUS (fetch from API)
  if (activeSection === 'leaderboard') {
    return <LeaderboardSection onBack={() => setActiveSection(null)} />;
  }
  
  // Section: Settings
  if (activeSection === 'settings') {
    return (
      <div className="h-full flex flex-col bg-background pb-[80px]" data-testid="settings-section">
        <div className="flex items-center gap-3 p-4 bg-surface">
          <button 
            onClick={() => setActiveSection(null)}
            className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-neutral-100 active:scale-95 transition-all"
          >
            <ChevronRight className="rotate-180" size={24} />
          </button>
          <h2 className="text-lg font-semibold text-neutral-900">Налаштування</h2>
        </div>
        
        <div className="flex-1 p-4 space-y-4 overflow-y-auto">
          <div className="glass-card-solid p-4">
            <div className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-3">Сповіщення</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-neutral-700">Push-сповіщення</span>
                <div className="w-11 h-6 bg-primary rounded-full relative">
                  <div className="absolute right-1 top-1 w-4 h-4 bg-white rounded-full" />
                </div>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-700">Тихі години</span>
                <span className="text-sm text-neutral-400">Вимк</span>
              </div>
            </div>
          </div>
          
          <div className="glass-card-solid p-4">
            <div className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-3">Радар</div>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-neutral-700">Радіус за замовч.</span>
                <span className="text-sm text-neutral-500 font-mono">{radarRadius}м</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-neutral-700">Автоактивація</span>
                <div className="w-11 h-6 bg-neutral-200 rounded-full relative">
                  <div className="absolute left-1 top-1 w-4 h-4 bg-white rounded-full shadow" />
                </div>
              </div>
            </div>
          </div>
          
          {/* Privacy Settings */}
          <div className="glass-card-solid p-4">
            <div className="text-xs font-medium text-neutral-400 uppercase tracking-wider mb-3">Конфіденційність</div>
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-neutral-700">Зберігання геолокації</span>
                </div>
                <div className="grid grid-cols-4 gap-2">
                  {[
                    { value: 'none', label: 'Ні' },
                    { value: '15m', label: '15хв' },
                    { value: '1h', label: '1год' },
                    { value: '24h', label: '24год' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => updatePrivacySettings('locationRetention', opt.value)}
                      className={`py-2 px-3 rounded-xl text-sm font-medium transition-all ${
                        privacySettings.locationRetention === opt.value
                          ? 'bg-primary text-white'
                          : 'bg-neutral-100 text-neutral-600'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
              
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-neutral-700">Точність локації</span>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { value: 'exact', label: 'Точна' },
                    { value: 'approx', label: 'Приблизна (±100м)' },
                  ].map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => updatePrivacySettings('locationPrecision', opt.value)}
                      className={`py-2 px-3 rounded-xl text-sm font-medium transition-all ${
                        privacySettings.locationPrecision === opt.value
                          ? 'bg-primary text-white'
                          : 'bg-neutral-100 text-neutral-600'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
            <p className="text-xs text-neutral-400 mt-3 leading-relaxed">
              Ми використовуємо геолокацію лише для створення сигналів. 
              Дані автоматично видаляються згідно з вашими налаштуваннями.
            </p>
          </div>
        </div>
      </div>
    );
  }
  
  // Main Profile
  return (
    <div className="h-full flex flex-col bg-background pb-[80px] overflow-y-auto no-scrollbar" data-testid="profile-page">
      {/* Header Card */}
      <div className="bg-surface p-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary/60 rounded-2xl flex items-center justify-center text-white">
            {displayUser.photoUrl ? (
              <img src={displayUser.photoUrl} alt="" className="w-full h-full rounded-2xl object-cover" />
            ) : (
              <User size={28} />
            )}
          </div>
          <div className="flex-1">
            <h2 className="text-xl font-bold text-neutral-900">
              {displayUser.firstName} {displayUser.lastName || ''}
            </h2>
            <span className="text-sm text-neutral-500">@{displayUser.username || 'user'}</span>
          </div>
          <div className="px-3 py-1.5 bg-warning/10 rounded-full flex items-center gap-1.5">
            <Zap size={14} className="text-warning" />
            <span className="text-sm font-semibold text-warning">Рів {stats.level}</span>
          </div>
        </div>
        
        {/* XP Progress */}
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-neutral-400 uppercase tracking-wider">Досвід</span>
            <span className="text-xs text-neutral-500 font-mono">{stats.xp} / {stats.xpNext} XP</span>
          </div>
          <div className="h-2 bg-neutral-100 rounded-full overflow-hidden">
            <div 
              className="h-full bg-gradient-to-r from-primary to-primary/70 rounded-full transition-all duration-500"
              style={{ width: `${xpProgress}%` }}
            />
          </div>
        </div>
      </div>
      
      <div className="p-4 space-y-4">
        {/* Streak Banner - shows when user has streak */}
        {streak > 0 && (
          <div className="glass-card-solid p-3 flex items-center gap-3 bg-gradient-to-r from-orange-50 to-amber-50">
            <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center">
              <Flame size={20} className="text-orange-500" />
            </div>
            <div className="flex-1">
              <div className="text-xs text-orange-600/70 uppercase tracking-wider">Streak</div>
              <div className="font-bold text-orange-600">{streak} {streak === 1 ? 'день' : 'днів'}</div>
            </div>
          </div>
        )}
        
        {/* Radar Status */}
        <div className="glass-card-solid p-4 flex items-center gap-4">
          <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${radarActive ? 'bg-success/10' : 'bg-neutral-100'}`}>
            <Target size={24} className={radarActive ? 'text-success' : 'text-neutral-400'} />
          </div>
          <div className="flex-1">
            <div className="text-xs text-neutral-400 uppercase tracking-wider">Статус радару</div>
            <div className="font-semibold text-neutral-900">{radarActive ? 'Активний' : 'Вимкнено'}</div>
          </div>
          <span className="px-3 py-1 bg-neutral-100 rounded-full text-sm font-mono text-neutral-600">{radarRadius}м</span>
        </div>
        
        {/* Stats Grid - 4 columns */}
        <div className="grid grid-cols-4 gap-2">
          {[
            { icon: Zap, value: stats.signalsSent, label: 'Сигн.', color: '#3B82F6' },
            { icon: CheckCircle, value: stats.signalsConfirmed, label: 'Підтв.', color: '#22C55E' },
            { icon: Shield, value: `${stats.trustScore}%`, label: 'Довіра', color: '#F59E0B' },
            { icon: Flame, value: streak || 0, label: 'Streak', color: '#F97316' },
          ].map((item, i) => (
            <div key={i} className="glass-card-solid p-3 text-center">
              <div 
                className="w-8 h-8 rounded-lg flex items-center justify-center mx-auto mb-1"
                style={{ background: `${item.color}15` }}
              >
                <item.icon size={16} style={{ color: item.color }} />
              </div>
              <div className="text-lg font-bold" style={{ color: '#1a1a1a' }}>{item.value}</div>
              <div className="text-[10px] text-neutral-500">{item.label}</div>
            </div>
          ))}
        </div>
        
        {/* Menu */}
        <div className="space-y-2">
          {[
            { icon: Share2, label: 'Реферали', action: () => openSection('referrals'), color: '#8B5CF6' },
            { icon: Trophy, label: 'Рейтинг', action: () => openSection('leaderboard'), color: '#F59E0B' },
            { 
              icon: Crown, 
              label: 'Підписка', 
              action: subscription?.isSubscribed ? () => {} : handleSubscribe,
              color: subscription?.isSubscribed ? '#22C55E' : '#3B82F6',
              badge: subscription?.isSubscribed ? 'PRO' : 'Free',
              extra: !subscription?.isSubscribed ? '⭐ 200' : null,
              loading: loadingSubscription,
            },
            { 
              icon: Send, 
              label: 'Телеграм-канал', 
              action: handleOpenChannel,
              color: channelSubscribed ? '#22C55E' : '#229ED9',
              badge: channelSubscribed ? 'Підписано' : 'Підписатись',
              loading: loadingChannel,
            },
            { icon: Settings, label: 'Налаштування', action: () => openSection('settings'), color: '#64748B' },
          ].map((item, i) => (
            <button
              key={i}
              onClick={item.action}
              disabled={item.loading}
              className="menu-item-modern"
            >
              <div 
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: `${item.color}15` }}
              >
                {item.loading ? (
                  <Loader2 size={20} className="animate-spin" style={{ color: item.color }} />
                ) : (
                  <item.icon size={20} style={{ color: item.color }} />
                )}
              </div>
              <span className="flex-1 text-left font-medium text-neutral-700">{item.label}</span>
              {item.badge && (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                  item.badge === 'PRO' ? 'bg-success/15 text-success' : 
                  item.badge === 'Підписано' ? 'bg-success/15 text-success' : 
                  item.badge === 'Підписатись' ? 'bg-blue-100 text-blue-600' :
                  'bg-neutral-100 text-neutral-500'
                }`}>
                  {item.badge}
                </span>
              )}
              {item.extra && (
                <span className="text-sm text-warning font-medium">{item.extra}</span>
              )}
              <ChevronRight size={18} className="text-neutral-300" />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
