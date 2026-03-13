/**
 * Geo Admin Page - Light Design (Telegram 2026 Style)
 * Protected admin panel with glassmorphism and green accents
 */
import { useState, useEffect, useCallback } from 'react';
import {
  LayoutDashboard,
  Radio,
  Users,
  Bot,
  Settings,
  BarChart3,
  FileText,
  LogOut,
  Trash2,
  Play,
  Pause,
  RefreshCw,
  ChevronRight,
  AlertTriangle,
  Wifi,
  Send,
  Key,
  Clock,
  MapPin,
  Activity,
  Zap,
  CheckCircle,
  XCircle,
  X,
  Eye,
  ArrowRight,
  MessageCircle
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// ==================== Login Screen ====================
function AdminLogin({ onLogin }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_key: key })
      });
      const data = await res.json();
      
      if (data.ok && data.token) {
        localStorage.setItem('geo_admin_token', data.token);
        onLogin(data.token);
      } else {
        setError('Невірний ключ доступу');
      }
    } catch (err) {
      setError('Помилка підключення');
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="glass-card p-8">
          <div className="flex items-center gap-4 mb-8">
            <div className="w-14 h-14 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-2xl flex items-center justify-center shadow-lg">
              <Radio className="w-7 h-7 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900">Geo Admin</h1>
              <p className="text-sm text-gray-500">Панель управління</p>
            </div>
          </div>
          
          <form onSubmit={handleSubmit}>
            <div className="relative mb-4">
              <Key className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="password"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder="Ключ доступу"
                className="w-full pl-12 pr-4 py-3.5 bg-gray-50 border border-gray-200 rounded-2xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 transition-all"
                autoFocus
              />
            </div>
            
            {error && (
              <div className="flex items-center gap-2 text-red-500 text-sm mb-4 bg-red-50 px-4 py-2 rounded-xl">
                <AlertTriangle className="w-4 h-4" />
                {error}
              </div>
            )}
            
            <button
              type="submit"
              disabled={loading || !key}
              className="w-full py-3.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 disabled:from-gray-300 disabled:to-gray-400 text-white font-semibold rounded-2xl transition-all flex items-center justify-center gap-2 shadow-lg shadow-emerald-200"
            >
              {loading ? (
                <RefreshCw className="w-5 h-5 animate-spin" />
              ) : (
                <>
                  <LogOut className="w-5 h-5" />
                  Увійти
                </>
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

// ==================== Navigation ====================
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'revenue', label: 'Revenue', icon: Activity },
  { id: 'signals', label: 'Сигнали', icon: Zap },
  { id: 'channels', label: 'Канали', icon: Radio },
  { id: 'ai-engine', label: 'AI Engine', icon: Bot },
  { id: 'sessions', label: 'Сесії', icon: Wifi },
  { id: 'users', label: 'Користувачі', icon: Users },
  { id: 'bot', label: 'Бот', icon: Bot },
  { id: 'analytics', label: 'Аналітика', icon: BarChart3 },
  { id: 'logs', label: 'Логи', icon: FileText },
  { id: 'settings', label: 'Налаштування', icon: Settings },
];

// ==================== Stat Card Component ====================
function StatCard({ title, value, subtitle, icon: Icon, color = 'emerald', trend }) {
  const colorStyles = {
    emerald: 'from-emerald-400 to-teal-500 shadow-emerald-200',
    blue: 'from-blue-400 to-indigo-500 shadow-blue-200',
    purple: 'from-purple-400 to-pink-500 shadow-purple-200',
    orange: 'from-orange-400 to-amber-500 shadow-orange-200',
    red: 'from-red-400 to-rose-500 shadow-red-200',
  };
  
  return (
    <div className="glass-card p-6 hover-lift">
      <div className="flex items-start justify-between mb-4">
        <div className={`w-12 h-12 bg-gradient-to-br ${colorStyles[color]} rounded-xl flex items-center justify-center shadow-lg`}>
          <Icon className="w-6 h-6 text-white" />
        </div>
        {trend && (
          <span className={`text-xs font-semibold px-2 py-1 rounded-lg ${trend > 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'}`}>
            {trend > 0 ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      <div className="text-3xl font-bold text-gray-900 mb-1">{value}</div>
      <div className="text-sm font-medium text-gray-600">{title}</div>
      {subtitle && <div className="text-xs text-gray-400 mt-1">{subtitle}</div>}
    </div>
  );
}

// ==================== Dashboard ====================
function DashboardView({ token }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchStats = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/geo-admin/dashboard`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.ok) setStats(data);
      } catch (err) {
        console.error('Dashboard fetch error:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, [token]);
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }
  
  if (!stats) {
    return <div className="text-gray-500">Помилка завантаження</div>;
  }
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Dashboard</h2>
        <span className="text-sm text-gray-500">
          <Clock className="w-4 h-4 inline mr-1" />
          Оновлено щойно
        </span>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard 
          title="Користувачі" 
          value={stats.users?.total || 0} 
          subtitle={`${stats.users?.radarEnabled || 0} з радаром`} 
          icon={Users}
          color="emerald"
        />
        <StatCard 
          title="Алерти сьогодні" 
          value={stats.alerts?.sentToday || 0} 
          subtitle={stats.alerts?.failedToday ? `${stats.alerts.failedToday} помилок` : 'Всі доставлені'}
          icon={Send}
          color="blue"
        />
        <StatCard 
          title="Сигнали 24г" 
          value={stats.signals?.last24h || 0} 
          subtitle={`${stats.signals?.reportsToday || 0} репортів`}
          icon={Activity}
          color="purple"
        />
        <StatCard 
          title="Активні канали" 
          value={stats.channels?.active || 0} 
          subtitle={`${stats.channels?.telegramIntel || 0} TG Intel`}
          icon={Radio}
          color="orange"
        />
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* MTProto Status */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">MTProto Статус</h3>
          <div className="flex items-center gap-3 mb-4">
            {stats.parsing?.mtprotoStatus === 'connected' ? (
              <>
                <div className="w-3 h-3 bg-emerald-500 rounded-full animate-pulse" />
                <span className="text-emerald-600 font-medium">Підключено</span>
              </>
            ) : (
              <>
                <div className="w-3 h-3 bg-gray-300 rounded-full" />
                <span className="text-gray-500 font-medium">Відключено</span>
              </>
            )}
          </div>
          <div className="flex items-center justify-between text-sm">
            <span className="text-gray-500">Постів за 24г</span>
            <span className="font-semibold text-gray-900">{stats.parsing?.posts24h || 0}</span>
          </div>
        </div>
        
        {/* Delivery Queue */}
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Черга доставки</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-500">В очікуванні</span>
              <span className="font-semibold text-orange-500">{stats.delivery?.pending || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Відправлено</span>
              <span className="font-semibold text-emerald-500">{stats.delivery?.sent || 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-500">Помилки</span>
              <span className="font-semibold text-red-500">{stats.delivery?.failed || 0}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==================== Revenue & Referrals ====================
function RevenueView({ token }) {
  const [stats, setStats] = useState(null);
  const [payouts, setPayouts] = useState([]);
  const [topReferrers, setTopReferrers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [revenueRes, payoutsRes, referrersRes] = await Promise.all([
        fetch(`${API_BASE}/api/geo-admin/revenue/stats`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE}/api/geo-admin/payouts/pending`, {
          headers: { 'Authorization': `Bearer ${token}` }
        }),
        fetch(`${API_BASE}/api/geo-admin/revenue/top-referrers`, {
          headers: { 'Authorization': `Bearer ${token}` }
        })
      ]);
      
      const [revenueData, payoutsData, referrersData] = await Promise.all([
        revenueRes.json(),
        payoutsRes.json(),
        referrersRes.json()
      ]);
      
      if (revenueData.ok) setStats(revenueData);
      if (payoutsData.ok) setPayouts(payoutsData.items || []);
      if (referrersData.ok) setTopReferrers(referrersData.items || []);
    } catch (err) {
      console.error('Revenue fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);
  
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  
  const handleApprovePayout = async (payoutId) => {
    const txHash = prompt('TX Hash (optional):');
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/payouts/${payoutId}/approve`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ tx_hash: txHash || '' })
      });
      if ((await res.json()).ok) fetchData();
    } catch (err) {
      console.error('Approve error:', err);
    }
  };
  
  const handleRejectPayout = async (payoutId) => {
    const reason = prompt('Причина відмови:');
    if (!reason) return;
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/payouts/${payoutId}/reject`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason })
      });
      if ((await res.json()).ok) fetchData();
    } catch (err) {
      console.error('Reject error:', err);
    }
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Revenue & Referrals</h2>
        <button
          onClick={fetchData}
          className="p-2 bg-white border border-gray-200 rounded-xl hover:bg-gray-50"
        >
          <RefreshCw className="w-5 h-5 text-gray-500" />
        </button>
      </div>
      
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card p-5">
          <div className="text-3xl font-bold text-emerald-600">${stats?.mrr?.toFixed(2) || '0.00'}</div>
          <div className="text-sm text-gray-500 mt-1">MRR</div>
        </div>
        <div className="glass-card p-5">
          <div className="text-3xl font-bold text-blue-600">${stats?.arr?.toFixed(2) || '0.00'}</div>
          <div className="text-sm text-gray-500 mt-1">ARR</div>
        </div>
        <div className="glass-card p-5">
          <div className="text-3xl font-bold text-purple-600">{stats?.activeSubscriptions || 0}</div>
          <div className="text-sm text-gray-500 mt-1">Active Subs</div>
        </div>
        <div className="glass-card p-5">
          <div className="text-3xl font-bold text-orange-600">{payouts.length}</div>
          <div className="text-sm text-gray-500 mt-1">Pending Payouts</div>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="flex gap-2 border-b border-gray-200">
        {['overview', 'payouts', 'referrers'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'overview' && 'Огляд'}
            {tab === 'payouts' && `Виплати (${payouts.length})`}
            {tab === 'referrers' && 'Топ рефералів'}
          </button>
        ))}
      </div>
      
      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Дохід за 30 днів</h3>
            <div className="text-4xl font-bold text-emerald-600 mb-2">${stats?.totalRevenue?.toFixed(2) || '0.00'}</div>
            <div className="text-sm text-gray-500">{stats?.totalPayments || 0} платежів</div>
          </div>
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Реферальна програма</h3>
            <div className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-500">Виплачено рефералам</span>
                <span className="font-semibold">${(stats?.totalRevenue * 0.3)?.toFixed(2) || '0.00'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Нетто дохід</span>
                <span className="font-semibold text-emerald-600">${(stats?.totalRevenue * 0.7)?.toFixed(2) || '0.00'}</span>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Payouts Tab */}
      {activeTab === 'payouts' && (
        <div className="glass-card overflow-hidden">
          {payouts.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Activity className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>Немає заявок на виплату</p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">ID</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">User</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Сума</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Метод</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Адреса</th>
                  <th className="text-right px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Дії</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {payouts.map(p => (
                  <tr key={p.payoutId} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-mono text-gray-600">{p.payoutId.slice(-8)}</td>
                    <td className="px-6 py-4 text-sm text-gray-900">{p.userId}</td>
                    <td className="px-6 py-4 text-sm font-semibold text-emerald-600">${p.amount?.toFixed(2)}</td>
                    <td className="px-6 py-4 text-sm text-gray-600 uppercase">{p.method}</td>
                    <td className="px-6 py-4 text-sm font-mono text-gray-500 truncate max-w-[150px]">{p.address || '—'}</td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleApprovePayout(p.payoutId)}
                          className="px-3 py-1 bg-emerald-500 hover:bg-emerald-600 text-white text-sm rounded-lg"
                        >
                          Approve
                        </button>
                        <button
                          onClick={() => handleRejectPayout(p.payoutId)}
                          className="px-3 py-1 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg"
                        >
                          Reject
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      
      {/* Top Referrers Tab */}
      {activeTab === 'referrers' && (
        <div className="glass-card overflow-hidden">
          {topReferrers.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <Users className="w-12 h-12 mx-auto mb-3 text-gray-300" />
              <p>Поки немає рефералів</p>
            </div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-100">
                <tr>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Rank</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">User</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Запрошено</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Активних</th>
                  <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Зароблено</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {topReferrers.map((r, i) => (
                  <tr key={r.userId} className="hover:bg-gray-50">
                    <td className="px-6 py-4">
                      <span className="text-2xl">{i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : `${i+1}.`}</span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-900">{r.userId}</td>
                    <td className="px-6 py-4 text-sm font-medium text-gray-600">{r.referralCount}</td>
                    <td className="px-6 py-4 text-sm font-medium text-emerald-600">{r.activeReferrals}</td>
                    <td className="px-6 py-4 text-sm font-bold text-emerald-600">${r.totalEarned?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ==================== Channels ====================
function ChannelsView({ token }) {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [adding, setAdding] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [showResults, setShowResults] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(null);
  
  // Posts modal state
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [posts, setPosts] = useState([]);
  const [postsLoading, setPostsLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  
  const fetchChannels = useCallback(async () => {
    setLoading(true);
    console.log('[ChannelsView] Fetching channels, token:', token ? 'present' : 'missing');
    try {
      const url = `${API_BASE}/api/geo-admin/channels`;
      console.log('[ChannelsView] Fetch URL:', url);
      const res = await fetch(url, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      console.log('[ChannelsView] Response status:', res.status);
      const data = await res.json();
      console.log('[ChannelsView] Response data:', data);
      if (data.ok) {
        console.log('[ChannelsView] Setting channels:', data.items?.length || 0);
        setChannels(data.items || []);
      } else {
        console.error('[ChannelsView] API returned not ok:', data);
      }
    } catch (err) {
      console.error('[ChannelsView] Fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);
  
  useEffect(() => {
    fetchChannels();
  }, [fetchChannels]);
  
  // Fetch posts for channel
  const fetchPosts = async (username) => {
    setPostsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/channels/${username}/posts?limit=100`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.ok) {
        setPosts(data.posts || []);
      }
    } catch (err) {
      console.error('Posts fetch error:', err);
    } finally {
      setPostsLoading(false);
    }
  };
  
  // Sync posts from Telegram
  const syncPosts = async (username) => {
    setSyncing(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/channels/${username}/sync?limit=100`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.ok) {
        // Reload posts and channels
        fetchPosts(username);
        fetchChannels();
      }
    } catch (err) {
      console.error('Sync error:', err);
    } finally {
      setSyncing(false);
    }
  };
  
  // Open posts modal
  const openPostsModal = (channel) => {
    setSelectedChannel(channel);
    fetchPosts(channel.username);
  };
  
  // Live search channel via MTProto
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setShowResults(false);
      setSearchError(null);
      return;
    }
    
    const query = searchQuery.toLowerCase().replace('@', '');
    
    // Debounce search - wait 500ms after typing
    if (query.length < 3) {
      setSearchResults([]);
      setShowResults(false);
      return;
    }
    
    // Check if already in our channels list (local check)
    const existingUsernames = new Set(channels.map(ch => ch.username.toLowerCase()));
    const alreadyInList = existingUsernames.has(query);
    
    const searchTimeout = setTimeout(async () => {
      setSearching(true);
      setSearchError(null);
      
      try {
        const res = await fetch(`${API_BASE}/api/geo-admin/channels/search/${query}`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        
        if (data.ok && data.channel) {
          // Channel found via MTProto
          const isAdded = data.alreadyAdded || alreadyInList;
          setSearchResults([{
            username: data.channel.username,
            title: data.channel.title,
            participantsCount: data.channel.participantsCount,
            avatarUrl: data.channel.avatarUrl,
            source: data.source,
            alreadyAdded: isAdded,
            isNew: !isAdded
          }]);
          setShowResults(true);
          if (isAdded) {
            setSearchError('Канал вже додано до списку');
          }
        } else {
          // Channel not found in Telegram - show option to try adding anyway
          if (alreadyInList) {
            setSearchResults([]);
            setShowResults(false);
            setSearchError('Канал вже додано до списку');
          } else {
            setSearchResults([{ username: query, isNew: true, notFound: true }]);
            setShowResults(true);
            if (data.error === 'NOT_FOUND') {
              setSearchError('Канал не знайдено в Telegram');
            }
          }
        }
      } catch (err) {
        console.error('Search error:', err);
        // Fallback - show option to add
        if (!alreadyInList) {
          setSearchResults([{ username: query, isNew: true }]);
          setShowResults(true);
        }
      } finally {
        setSearching(false);
      }
    }, 500);
    
    return () => clearTimeout(searchTimeout);
  }, [searchQuery, channels, token]);
  
  const addChannel = async (username) => {
    if (!username.trim()) return;
    setAdding(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/channels`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim() })
      });
      const data = await res.json();
      if (data.ok) {
        setSearchQuery('');
        setShowResults(false);
        fetchChannels();
      }
    } catch (err) {
      console.error('Add channel error:', err);
    } finally {
      setAdding(false);
    }
  };
  
  const toggleChannel = async (username, enabled) => {
    try {
      await fetch(`${API_BASE}/api/geo-admin/channels/${username}`, {
        method: 'PATCH',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !enabled })
      });
      fetchChannels();
    } catch (err) {
      console.error('Toggle error:', err);
    }
  };
  
  const deleteChannel = async (username) => {
    if (!window.confirm(`Видалити канал @${username}?`)) return;
    try {
      await fetch(`${API_BASE}/api/geo-admin/channels/${username}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      fetchChannels();
    } catch (err) {
      console.error('Delete error:', err);
    }
  };
  
  // Filter displayed channels based on search
  const filteredChannels = searchQuery.trim() 
    ? channels.filter(ch => 
        ch.username.toLowerCase().includes(searchQuery.toLowerCase().replace('@', '')) ||
        (ch.title && ch.title.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : channels;
  
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Канали</h2>
      
      {/* Unified search + add field */}
      <div className="relative">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Пошук або додати канал (@username)"
          className="w-full px-4 py-3 bg-white border border-gray-200 rounded-2xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && searchQuery.trim().length >= 3) {
              const query = searchQuery.toLowerCase().replace('@', '');
              const exists = channels.some(ch => ch.username.toLowerCase() === query);
              if (!exists) {
                addChannel(query);
              }
            }
          }}
        />
        
        {/* Search indicator */}
        {searching && (
          <div className="absolute right-4 top-1/2 -translate-y-1/2">
            <RefreshCw className="w-5 h-5 text-emerald-500 animate-spin" />
          </div>
        )}
        
        {/* Dropdown suggestion with channel info */}
        {showResults && searchResults.length > 0 && (
          <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-gray-200 rounded-2xl shadow-lg z-10 overflow-hidden">
            {searchResults.map((result) => (
              <button
                key={result.username}
                onClick={() => !result.alreadyAdded && addChannel(result.username)}
                disabled={adding || result.alreadyAdded}
                className={`w-full flex items-center justify-between px-4 py-3 transition-colors text-left ${
                  result.alreadyAdded ? 'bg-gray-50 cursor-not-allowed' : 'hover:bg-emerald-50'
                }`}
              >
                <div className="flex items-center gap-3">
                  {result.avatarUrl ? (
                    <img src={`${API_BASE}${result.avatarUrl}`} alt="" className="w-10 h-10 rounded-full object-cover" />
                  ) : (
                    <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center">
                      <Radio className="w-5 h-5 text-white" />
                    </div>
                  )}
                  <div>
                    <div className="font-medium text-gray-900">@{result.username}</div>
                    {result.title && result.title !== result.username && (
                      <div className="text-sm text-gray-500">{result.title}</div>
                    )}
                    {result.participantsCount && (
                      <div className="text-xs text-gray-400">{result.participantsCount.toLocaleString()} підписників</div>
                    )}
                  </div>
                </div>
                <div className="text-right">
                  {result.alreadyAdded ? (
                    <span className="text-sm text-gray-400">Вже додано</span>
                  ) : result.notFound ? (
                    <span className="text-sm text-orange-500 font-medium">Спробувати додати</span>
                  ) : (
                    <span className="text-sm text-emerald-600 font-medium">
                      {adding ? <RefreshCw className="w-4 h-4 animate-spin" /> : 'Додати канал'}
                    </span>
                  )}
                  {result.source === 'mtproto' && !result.alreadyAdded && (
                    <div className="text-xs text-emerald-500 mt-0.5">✓ Знайдено в Telegram</div>
                  )}
                </div>
              </button>
            ))}
            {searchError && (
              <div className="px-4 py-2 bg-orange-50 text-orange-600 text-sm border-t border-orange-100">
                {searchError}
              </div>
            )}
          </div>
        )}
      </div>
      
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="w-6 h-6 text-emerald-500 animate-spin" />
          </div>
        ) : filteredChannels.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Radio className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p>{searchQuery ? 'Канал не знайдено' : 'Каналів не знайдено'}</p>
            {searchQuery && searchQuery.length >= 3 && (
              <p className="text-sm mt-2">Натисніть Enter для додавання @{searchQuery.replace('@', '')}</p>
            )}
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Канал</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Статус</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Geo Events</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Пости</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Пріоритет</th>
                <th className="text-right px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filteredChannels.map((ch) => (
                <tr key={ch.username} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      {ch.avatarUrl ? (
                        <img 
                          src={`${API_BASE}${ch.avatarUrl}`} 
                          alt="" 
                          className="w-10 h-10 rounded-full object-cover"
                          onError={(e) => { e.target.style.display = 'none' }}
                        />
                      ) : (
                        <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center">
                          <Radio className="w-5 h-5 text-white" />
                        </div>
                      )}
                      <div>
                        <div className="font-medium text-gray-900">@{ch.username}</div>
                        {ch.title && ch.title !== ch.username && <div className="text-sm text-gray-500">{ch.title}</div>}
                        {ch.participantsCount > 0 && <div className="text-xs text-gray-400">{ch.participantsCount.toLocaleString()} підписників</div>}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    {ch.enabled ? (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-emerald-50 text-emerald-600 text-xs font-semibold rounded-full">
                        <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                        Активний
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-3 py-1 bg-gray-100 text-gray-500 text-xs font-semibold rounded-full">
                        <Pause className="w-3 h-3" />
                        Пауза
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{ch.geoEventsCount || 0}</td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{ch.postsCount || 0}</td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{ch.priority || 5}</td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openPostsModal(ch)}
                        className="p-2 hover:bg-blue-50 rounded-lg transition-colors"
                        title="Переглянути пости"
                      >
                        <FileText className="w-4 h-4 text-blue-500" />
                      </button>
                      <button
                        onClick={() => toggleChannel(ch.username, ch.enabled)}
                        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                        title={ch.enabled ? 'Пауза' : 'Увімкнути'}
                      >
                        {ch.enabled ? (
                          <Pause className="w-4 h-4 text-orange-500" />
                        ) : (
                          <Play className="w-4 h-4 text-emerald-500" />
                        )}
                      </button>
                      <button
                        onClick={() => deleteChannel(ch.username)}
                        className="p-2 hover:bg-red-50 rounded-lg transition-colors"
                        title="Видалити"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      
      {/* Posts Modal */}
      {selectedChannel && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-3">
                {selectedChannel.avatarUrl ? (
                  <img src={`${API_BASE}${selectedChannel.avatarUrl}`} alt="" className="w-12 h-12 rounded-full object-cover" />
                ) : (
                  <div className="w-12 h-12 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-full flex items-center justify-center">
                    <Radio className="w-6 h-6 text-white" />
                  </div>
                )}
                <div>
                  <h2 className="text-lg font-bold text-gray-900">@{selectedChannel.username}</h2>
                  <p className="text-sm text-gray-500">{selectedChannel.title}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => syncPosts(selectedChannel.username)}
                  disabled={syncing}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-xl hover:bg-emerald-600 transition-colors disabled:opacity-50"
                >
                  <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
                  {syncing ? 'Синхронізація...' : 'Синхронізувати'}
                </button>
                <button
                  onClick={() => setSelectedChannel(null)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                  <X className="w-5 h-5 text-gray-500" />
                </button>
              </div>
            </div>
            
            {/* Modal Body - Posts List */}
            <div className="flex-1 overflow-y-auto p-6">
              {postsLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
                </div>
              ) : posts.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <FileText className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                  <p>Постів поки немає</p>
                  <p className="text-sm mt-2">Натисніть "Синхронізувати" щоб завантажити пости з Telegram</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {posts.map((post, idx) => (
                    <div key={post.messageId || idx} className="bg-gray-50 rounded-xl p-4 hover:bg-gray-100 transition-colors">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0">
                          <p className="text-gray-900 whitespace-pre-wrap break-words">{post.text || '(без тексту)'}</p>
                        </div>
                        <div className="flex-shrink-0 text-right">
                          <div className="text-xs text-gray-400">
                            {post.date ? new Date(post.date).toLocaleString('uk-UA') : ''}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <Eye className="w-3 h-3" />
                          {post.views?.toLocaleString() || 0}
                        </span>
                        <span className="flex items-center gap-1">
                          <ArrowRight className="w-3 h-3" />
                          {post.forwards || 0} репостів
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageCircle className="w-3 h-3" />
                          {post.replies || 0}
                        </span>
                        {post.hasMedia && (
                          <span className="text-blue-500">📎 медіа</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            {/* Modal Footer */}
            <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 rounded-b-2xl">
              <div className="flex items-center justify-between text-sm text-gray-500">
                <span>Всього постів: {posts.length}</span>
                <span>Останнє оновлення: {selectedChannel.lastParsedAt ? new Date(selectedChannel.lastParsedAt).toLocaleString('uk-UA') : 'Ніколи'}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== Sessions ====================
function SessionsView({ token }) {
  const [sessions, setSessions] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [sessionsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/geo-admin/sessions`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/geo-admin/sessions/stats`, { headers: { 'Authorization': `Bearer ${token}` } })
      ]);
      const sessionsData = await sessionsRes.json();
      const statsData = await statsRes.json();
      if (sessionsData.ok) setSessions(sessionsData.items || []);
      if (statsData.ok) setStats(statsData);
    } catch (err) {
      console.error('Sessions fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);
  
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">MTProto Сесії</h2>
        <button className="px-4 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 text-white font-medium rounded-xl shadow-lg shadow-emerald-200 transition-all">
          Додати сесію
        </button>
      </div>
      
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-gray-900">{stats.totalSessions}</div>
            <div className="text-sm text-gray-500">Всього сесій</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-emerald-500">{stats.active}</div>
            <div className="text-sm text-gray-500">Активних</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-blue-500">{stats.totalThreads}</div>
            <div className="text-sm text-gray-500">Потоків</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-purple-500">{stats.totalChannels}</div>
            <div className="text-sm text-gray-500">Каналів</div>
          </div>
        </div>
      )}
      
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="w-6 h-6 text-emerald-500 animate-spin" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Wifi className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="mb-2">Сесій не налаштовано</p>
            <p className="text-sm text-gray-400">Додайте MTProto сесію для парсингу каналів</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Сесія</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Статус</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Потоки</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Канали</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Rate Limit</th>
                <th className="text-right px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sessions.map((s) => (
                <tr key={s.sessionId} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium text-gray-900">{s.name}</div>
                    <div className="text-sm text-gray-500">@{s.sessionUser?.username || 'unknown'}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold rounded-full ${
                      s.status === 'active' ? 'bg-emerald-50 text-emerald-600' :
                      s.status === 'cooldown' ? 'bg-orange-50 text-orange-600' :
                      s.status === 'invalid' ? 'bg-red-50 text-red-600' :
                      'bg-gray-100 text-gray-500'
                    }`}>
                      {s.status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{s.activeThreads}/{s.maxThreads}</td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{s.channelsAssigned}/{s.channelsLimit}</td>
                  <td className="px-6 py-4">
                    <span className={s.rateLimitState === 'ok' ? 'text-emerald-500 font-medium' : 'text-orange-500 font-medium'}>
                      {s.rateLimitState}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors" title="Тест">
                      <RefreshCw className="w-4 h-4 text-emerald-500" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ==================== Users ====================
function UsersView({ token }) {
  const [users, setUsers] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        const [usersRes, analyticsRes] = await Promise.all([
          fetch(`${API_BASE}/api/geo-admin/users`, { headers: { 'Authorization': `Bearer ${token}` } }),
          fetch(`${API_BASE}/api/geo-admin/users/analytics`, { headers: { 'Authorization': `Bearer ${token}` } })
        ]);
        const usersData = await usersRes.json();
        const analyticsData = await analyticsRes.json();
        if (usersData.ok) setUsers(usersData.items || []);
        if (analyticsData.ok) setAnalytics(analyticsData);
      } catch (err) {
        console.error('Users fetch error:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [token]);
  
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Користувачі</h2>
      
      {analytics && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-gray-900">{analytics.total}</div>
            <div className="text-sm text-gray-500">Всього</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-emerald-500">{analytics.radarEnabled}</div>
            <div className="text-sm text-gray-500">Радар ({analytics.radarRate}%)</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-blue-500">{analytics.active7d}</div>
            <div className="text-sm text-gray-500">Активні 7д</div>
          </div>
          <div className="glass-card p-5">
            <div className="text-2xl font-bold text-purple-500">{analytics.newToday}</div>
            <div className="text-sm text-gray-500">Нові сьогодні</div>
          </div>
        </div>
      )}
      
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="w-6 h-6 text-emerald-500 animate-spin" />
          </div>
        ) : users.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Users className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p>Користувачів поки немає</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Користувач</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Радар</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Локація</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Алерти</th>
                <th className="text-left px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Репорти</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map((u) => (
                <tr key={u.actorId} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium text-gray-900">@{u.username || 'unknown'}</div>
                    <div className="text-xs text-gray-400">{u.actorId}</div>
                  </td>
                  <td className="px-6 py-4">
                    {u.radarEnabled ? (
                      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-emerald-50 text-emerald-600 text-xs font-semibold rounded-full">
                        <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
                        ON
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">OFF</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600 text-sm">
                    {u.lastLat ? (
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3 text-emerald-500" />
                        {u.lastLat.toFixed(3)}, {u.lastLng.toFixed(3)}
                      </span>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{u.alertsReceived || 0}</td>
                  <td className="px-6 py-4 text-gray-600 font-medium">{u.reportsSubmitted || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ==================== Bot Control ====================
function BotView({ token }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [broadcastText, setBroadcastText] = useState('');
  const [broadcastTarget, setBroadcastTarget] = useState('all');
  const [broadcastHistory, setBroadcastHistory] = useState([]);
  const [sending, setSending] = useState(false);
  const [testResult, setTestResult] = useState(null);
  
  const fetchData = useCallback(async () => {
    try {
      const [statusRes, historyRes] = await Promise.all([
        fetch(`${API_BASE}/api/geo-admin/bot/status`, { headers: { 'Authorization': `Bearer ${token}` } }),
        fetch(`${API_BASE}/api/geo-admin/broadcast/history?limit=5`, { headers: { 'Authorization': `Bearer ${token}` } })
      ]);
      const statusData = await statusRes.json();
      const historyData = await historyRes.json();
      if (statusData.ok) setStatus(statusData);
      if (historyData.ok) setBroadcastHistory(historyData.items || []);
    } catch (err) {
      console.error('Bot data error:', err);
    } finally {
      setLoading(false);
    }
  }, [token]);
  
  useEffect(() => {
    fetchData();
  }, [fetchData]);
  
  const handleTestBroadcast = async () => {
    if (!broadcastText.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/broadcast/test`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: broadcastText, target: broadcastTarget })
      });
      const data = await res.json();
      setTestResult(data);
    } catch (err) {
      console.error('Test broadcast error:', err);
    }
  };
  
  const handleSendBroadcast = async () => {
    if (!broadcastText.trim()) return;
    if (!window.confirm(`Надіслати повідомлення ${testResult?.targetUsers || '?'} користувачам?`)) return;
    
    setSending(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/broadcast/send`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: broadcastText, target: broadcastTarget })
      });
      const data = await res.json();
      if (data.ok) {
        alert(`Надіслано: ${data.sent}, Помилок: ${data.failed}`);
        setBroadcastText('');
        setTestResult(null);
        fetchData();
      }
    } catch (err) {
      console.error('Send broadcast error:', err);
    } finally {
      setSending(false);
    }
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Бот</h2>
      
      {status && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Інформація</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Username</span>
                <span className="font-semibold text-gray-900">@{status.botInfo?.username || '—'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Ім'я</span>
                <span className="text-gray-700">{status.botInfo?.first_name || '—'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Статус</span>
                {status.botConfigured ? (
                  <span className="inline-flex items-center gap-1.5 text-emerald-600 font-medium">
                    <div className="w-2 h-2 bg-emerald-500 rounded-full" />
                    Налаштовано
                  </span>
                ) : (
                  <span className="text-red-500">Не налаштовано</span>
                )}
              </div>
            </div>
          </div>
          
          <div className="glass-card p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Webhook</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Статус</span>
                {status.webhook?.active ? (
                  <span className="inline-flex items-center gap-1.5 text-emerald-600 font-medium">
                    <div className="w-2 h-2 bg-emerald-500 rounded-full" />
                    Активний
                  </span>
                ) : (
                  <span className="text-orange-500">Неактивний</span>
                )}
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">В черзі</span>
                <span className="font-medium text-gray-700">{status.webhook?.pendingUpdates || 0}</span>
              </div>
              {status.webhook?.lastError && (
                <div className="text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">{status.webhook.lastError}</div>
              )}
            </div>
          </div>
          
          <div className="glass-card p-6 md:col-span-2">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Статистика доставки</h3>
            <div className="grid grid-cols-4 gap-6">
              <div>
                <div className="text-3xl font-bold text-orange-500">{status.delivery?.pending || 0}</div>
                <div className="text-sm text-gray-500">В очікуванні</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-emerald-500">{status.delivery?.sentToday || 0}</div>
                <div className="text-sm text-gray-500">Сьогодні</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-red-500">{status.delivery?.failedToday || 0}</div>
                <div className="text-sm text-gray-500">Помилок</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-blue-500">{status.delivery?.alertsSentToday || 0}</div>
                <div className="text-sm text-gray-500">Алертів</div>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Broadcast Section */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">📢 Розсилка</h3>
        
        <div className="space-y-4">
          {/* Target selector */}
          <div className="flex gap-3">
            {[
              { value: 'all', label: 'Всі користувачі' },
              { value: 'subscribed', label: 'Підписники' },
              { value: 'radar', label: 'З радаром' }
            ].map(opt => (
              <button
                key={opt.value}
                onClick={() => { setBroadcastTarget(opt.value); setTestResult(null); }}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
                  broadcastTarget === opt.value
                    ? 'bg-emerald-500 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          
          {/* Message textarea */}
          <textarea
            value={broadcastText}
            onChange={(e) => { setBroadcastText(e.target.value); setTestResult(null); }}
            placeholder="Текст повідомлення (Markdown)..."
            rows={4}
            className="w-full px-4 py-3 bg-white border border-gray-200 rounded-xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-emerald-400 resize-none"
          />
          
          {/* Test result */}
          {testResult && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
              <div className="text-blue-800 font-medium">
                Буде надіслано: <span className="text-blue-600 text-xl">{testResult.targetUsers}</span> користувачам
              </div>
            </div>
          )}
          
          {/* Action buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleTestBroadcast}
              disabled={!broadcastText.trim()}
              className="px-4 py-2.5 bg-gray-100 hover:bg-gray-200 disabled:bg-gray-50 text-gray-700 disabled:text-gray-400 font-medium rounded-xl transition-colors"
            >
              Перевірити
            </button>
            <button
              onClick={handleSendBroadcast}
              disabled={!broadcastText.trim() || !testResult || sending}
              className="px-4 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 disabled:from-gray-300 disabled:to-gray-400 text-white font-medium rounded-xl transition-all shadow-lg shadow-emerald-200"
            >
              {sending ? <RefreshCw className="w-4 h-4 animate-spin" /> : 'Надіслати'}
            </button>
          </div>
        </div>
      </div>
      
      {/* Broadcast History */}
      {broadcastHistory.length > 0 && (
        <div className="glass-card p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Історія розсилок</h3>
          <div className="space-y-3">
            {broadcastHistory.map(b => (
              <div key={b.broadcastId} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                <div>
                  <div className="text-sm text-gray-700 truncate max-w-md">{b.text}</div>
                  <div className="text-xs text-gray-400 mt-1">
                    {new Date(b.startedAt).toLocaleString('uk-UA')} • {b.target}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold text-emerald-600">{b.sent} надіслано</div>
                  {b.failed > 0 && <div className="text-xs text-red-500">{b.failed} помилок</div>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ==================== AI Engine ====================
function AIEngineView({ token }) {
  const [settings, setSettings] = useState({
    enabled: false,
    openai_key: '',
    openai_key_set: false,
    model: 'gpt-4o-mini',
    confidence_threshold: 0.6
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testText, setTestText] = useState('');
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [slangDict, setSlangDict] = useState({ default: {}, custom: {} });
  const [newSlang, setNewSlang] = useState({ word: '', meaning: '' });
  
  // Fetch settings
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const [settingsRes, slangRes] = await Promise.all([
          fetch(`${API_BASE}/api/signal-intel/settings`),
          fetch(`${API_BASE}/api/signal-intel/slang`)
        ]);
        
        const settingsData = await settingsRes.json();
        const slangData = await slangRes.json();
        
        if (settingsData.ok) setSettings(settingsData.settings);
        if (slangData.ok) setSlangDict(slangData);
      } catch (err) {
        console.error('Settings fetch error:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchSettings();
  }, []);
  
  // Save settings
  const saveSettings = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/signal-intel/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      const data = await res.json();
      if (data.ok) {
        alert('Налаштування збережено!');
      }
    } catch (err) {
      console.error('Save error:', err);
    } finally {
      setSaving(false);
    }
  };
  
  // Test signal processing
  const testProcess = async () => {
    if (!testText.trim()) return;
    setTesting(true);
    setTestResult(null);
    
    try {
      const res = await fetch(`${API_BASE}/api/signal-intel/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: testText })
      });
      const data = await res.json();
      setTestResult(data);
    } catch (err) {
      console.error('Test error:', err);
      setTestResult({ ok: false, error: err.message });
    } finally {
      setTesting(false);
    }
  };
  
  // Add slang
  const addSlang = async () => {
    if (!newSlang.word || !newSlang.meaning) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/signal-intel/slang`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newSlang)
      });
      const data = await res.json();
      if (data.ok) {
        setSlangDict(prev => ({
          ...prev,
          custom: { ...prev.custom, [newSlang.word]: newSlang.meaning }
        }));
        setNewSlang({ word: '', meaning: '' });
      }
    } catch (err) {
      console.error('Add slang error:', err);
    }
  };
  
  // Process channel posts
  const processChannel = async (username) => {
    try {
      const res = await fetch(`${API_BASE}/api/signal-intel/batch/channel/${username}?limit=50`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.ok) {
        alert(`Оброблено ${data.postsProcessed} постів, знайдено ${data.signalsExtracted} сигналів, збережено ${data.signalsSaved}`);
      }
    } catch (err) {
      console.error('Process channel error:', err);
    }
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 text-emerald-500 animate-spin" />
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">AI Signal Engine</h2>
        <div className={`px-3 py-1 rounded-full text-sm font-medium ${settings.enabled ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>
          {settings.enabled ? 'AI Увімкнено' : 'AI Вимкнено'}
        </div>
      </div>
      
      {/* Settings Card */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Налаштування OpenAI</h3>
        
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Увімкнути AI класифікацію</label>
            <button
              onClick={() => setSettings(s => ({ ...s, enabled: !s.enabled }))}
              className={`w-12 h-6 rounded-full transition-colors ${settings.enabled ? 'bg-emerald-500' : 'bg-gray-300'}`}
            >
              <div className={`w-5 h-5 bg-white rounded-full shadow transform transition-transform ${settings.enabled ? 'translate-x-6' : 'translate-x-0.5'}`} />
            </button>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">OpenAI API Key</label>
            <input
              type="password"
              value={settings.openai_key || ''}
              onChange={(e) => setSettings(s => ({ ...s, openai_key: e.target.value }))}
              placeholder={settings.openai_key_set ? '••••••••' : 'sk-...'}
              className="w-full px-4 py-2 border border-gray-200 rounded-xl focus:outline-none focus:border-emerald-400"
            />
            {settings.openai_key_set && <p className="text-xs text-gray-500 mt-1">Ключ вже встановлено</p>}
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Модель</label>
            <select
              value={settings.model}
              onChange={(e) => setSettings(s => ({ ...s, model: e.target.value }))}
              className="w-full px-4 py-2 border border-gray-200 rounded-xl focus:outline-none focus:border-emerald-400"
            >
              <option value="gpt-4o-mini">GPT-4o Mini (швидка, дешева)</option>
              <option value="gpt-4o">GPT-4o (точна)</option>
              <option value="gpt-3.5-turbo">GPT-3.5 Turbo (бюджетна)</option>
            </select>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Поріг впевненості: {settings.confidence_threshold}
            </label>
            <input
              type="range"
              min="0.3"
              max="0.9"
              step="0.05"
              value={settings.confidence_threshold}
              onChange={(e) => setSettings(s => ({ ...s, confidence_threshold: parseFloat(e.target.value) }))}
              className="w-full"
            />
            <p className="text-xs text-gray-500">Сигнали з впевненістю нижче цього порогу будуть відхилені</p>
          </div>
          
          <button
            onClick={saveSettings}
            disabled={saving}
            className="w-full py-2 bg-emerald-500 text-white rounded-xl hover:bg-emerald-600 transition-colors disabled:opacity-50"
          >
            {saving ? 'Збереження...' : 'Зберегти налаштування'}
          </button>
        </div>
      </div>
      
      {/* Test Panel */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Тест парсингу</h3>
        
        <textarea
          value={testText}
          onChange={(e) => setTestText(e.target.value)}
          placeholder="Вставте текст з Telegram для тестування...&#10;&#10;Приклад:&#10;На кульженка сірий бус зупинили хлопця&#10;Вул.виговського бп&#10;Оболонь чисто"
          rows={5}
          className="w-full px-4 py-3 border border-gray-200 rounded-xl focus:outline-none focus:border-emerald-400 mb-4"
        />
        
        <button
          onClick={testProcess}
          disabled={testing || !testText.trim()}
          className="w-full py-2 bg-blue-500 text-white rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50 mb-4"
        >
          {testing ? 'Обробка...' : 'Тестувати парсинг'}
        </button>
        
        {testResult && (
          <div className="bg-gray-50 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium">Результат:</span>
              <span className="text-sm text-gray-500">{testResult.count || 0} сигналів знайдено</span>
            </div>
            
            {testResult.signals?.map((sig, idx) => (
              <div key={idx} className="bg-white rounded-lg p-3 mb-2 border border-gray-100">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold text-white ${
                    sig.type === 'police' ? 'bg-blue-500' :
                    sig.type === 'detention' ? 'bg-red-500' :
                    sig.type === 'checkpoint' ? 'bg-orange-500' :
                    sig.type === 'raid' ? 'bg-purple-500' :
                    sig.type === 'tck' ? 'bg-green-500' :
                    'bg-gray-500'
                  }`}>
                    {sig.type?.toUpperCase()}
                  </span>
                  <span className="text-sm text-gray-600">confidence: {(sig.confidence * 100).toFixed(0)}%</span>
                  {sig.aiUsed && <span className="text-xs bg-purple-100 text-purple-600 px-1.5 rounded">AI</span>}
                </div>
                {sig.locationName && (
                  <div className="text-sm text-gray-700">📍 {sig.locationName}</div>
                )}
                {sig.lat && sig.lng && (
                  <div className="text-xs text-gray-400">{sig.lat.toFixed(4)}, {sig.lng.toFixed(4)}</div>
                )}
                <div className="text-xs text-gray-500 mt-1 truncate">{sig.originalText}</div>
              </div>
            ))}
          </div>
        )}
      </div>
      
      {/* Slang Dictionary */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">
          Словник сленгу ({Object.keys(slangDict.default || {}).length + Object.keys(slangDict.custom || {}).length} слів)
        </h3>
        
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={newSlang.word}
            onChange={(e) => setNewSlang(s => ({ ...s, word: e.target.value }))}
            placeholder="Слово"
            className="flex-1 px-3 py-2 border border-gray-200 rounded-xl"
          />
          <input
            type="text"
            value={newSlang.meaning}
            onChange={(e) => setNewSlang(s => ({ ...s, meaning: e.target.value }))}
            placeholder="Значення"
            className="flex-1 px-3 py-2 border border-gray-200 rounded-xl"
          />
          <button
            onClick={addSlang}
            className="px-4 py-2 bg-emerald-500 text-white rounded-xl hover:bg-emerald-600"
          >
            Додати
          </button>
        </div>
        
        <div className="max-h-48 overflow-y-auto">
          <div className="grid grid-cols-2 gap-2 text-sm">
            {Object.entries(slangDict.custom || {}).map(([word, meaning]) => (
              <div key={word} className="flex items-center justify-between bg-emerald-50 rounded px-2 py-1">
                <span><strong>{word}</strong> → {meaning}</span>
                <button className="text-red-500 hover:text-red-700 text-xs">×</button>
              </div>
            ))}
            {Object.entries(slangDict.default || {}).slice(0, 20).map(([word, meaning]) => (
              <div key={word} className="flex items-center justify-between bg-gray-50 rounded px-2 py-1 text-gray-600">
                <span><strong>{word}</strong> → {meaning}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      
      {/* Signal Types */}
      <div className="glass-card p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Типи сигналів</h3>
        
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { type: 'police', label: 'Поліція', icon: '🚓', color: 'blue' },
            { type: 'detention', label: 'Затримання', icon: '🧟', color: 'red' },
            { type: 'checkpoint', label: 'Блокпост', icon: '🚧', color: 'orange' },
            { type: 'raid', label: 'Облава', icon: '🧟‍♂️', color: 'purple' },
            { type: 'tck', label: 'ТЦК', icon: '🟢', color: 'green' },
            { type: 'weather', label: 'Погода', icon: '🌧', color: 'gray' },
            { type: 'safe', label: 'Безпечно', icon: '✅', color: 'emerald' },
            { type: 'trash', label: 'Сміття', icon: '🗑', color: 'gray' },
          ].map(({ type, label, icon, color }) => (
            <div key={type} className={`p-3 rounded-xl border-2 border-${color}-200 bg-${color}-50`}>
              <div className="text-2xl mb-1">{icon}</div>
              <div className="font-medium text-gray-900">{label}</div>
              <div className="text-xs text-gray-500">{type}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ==================== Signals Management ====================
function SignalsView({ token }) {
  const [signals, setSignals] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [eventTypes, setEventTypes] = useState([]);
  const [selectedSignals, setSelectedSignals] = useState([]);
  
  const fetchSignals = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '50', hours: '48' });
      if (search) params.append('search', search);
      if (statusFilter) params.append('status', statusFilter);
      if (eventTypeFilter) params.append('event_type', eventTypeFilter);
      
      const res = await fetch(`${API_BASE}/api/geo-admin/signals?${params}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      const data = await res.json();
      if (data.ok) {
        setSignals(data.items || []);
        setStats(data.stats);
      }
    } catch (err) {
      console.error('Signals fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter, eventTypeFilter]);
  
  // Load signals when filters change
  useEffect(() => {
    fetchSignals();
  }, [fetchSignals]);
  
  // Load event types once on mount
  useEffect(() => {
    const loadEventTypes = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/geo-admin/signals/event-types`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await res.json();
        if (data.ok) setEventTypes(data.eventTypes || []);
      } catch (err) {
        console.error('Event types fetch error:', err);
      }
    };
    loadEventTypes();
  }, [token]);
  
  const handleConfirm = async (signalId) => {
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/signals/${signalId}/confirm`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if ((await res.json()).ok) fetchSignals();
    } catch (err) { console.error('Confirm error:', err); }
  };
  
  const handleDismiss = async (signalId) => {
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/signals/${signalId}/dismiss`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if ((await res.json()).ok) fetchSignals();
    } catch (err) { console.error('Dismiss error:', err); }
  };
  
  const handleDelete = async (signalId) => {
    if (!window.confirm('Видалити сигнал?')) return;
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/signals/${signalId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if ((await res.json()).ok) fetchSignals();
    } catch (err) { console.error('Delete error:', err); }
  };
  
  const handleBulkConfirm = async () => {
    if (selectedSignals.length === 0) return;
    try {
      const res = await fetch(`${API_BASE}/api/geo-admin/signals/bulk-status`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ signal_ids: selectedSignals, status: 'confirmed' })
      });
      if ((await res.json()).ok) {
        setSelectedSignals([]);
        fetchSignals();
      }
    } catch (err) { console.error('Bulk confirm error:', err); }
  };
  
  const toggleSelect = (signalId) => {
    setSelectedSignals(prev => 
      prev.includes(signalId) ? prev.filter(id => id !== signalId) : [...prev, signalId]
    );
  };
  
  const getStatusBadge = (status, truthScore) => {
    const styles = {
      confirmed: 'bg-emerald-50 text-emerald-600 border-emerald-200',
      medium: 'bg-blue-50 text-blue-600 border-blue-200',
      weak: 'bg-orange-50 text-orange-600 border-orange-200',
      raw: 'bg-gray-100 text-gray-600 border-gray-200',
      dismissed: 'bg-red-50 text-red-600 border-red-200'
    };
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full border ${styles[status] || styles.raw}`}>
        {status === 'confirmed' && <CheckCircle className="w-3 h-3" />}
        {status === 'dismissed' && <XCircle className="w-3 h-3" />}
        {status} ({Math.round((truthScore || 0) * 100)}%)
      </span>
    );
  };
  
  const formatEventType = (type) => {
    const labels = {
      military_movement: 'Військовий рух',
      explosion: 'Вибух',
      air_alert: 'Повітряна тривога',
      missile: 'Ракета',
      drone: 'Дрон',
      gunfire: 'Стрілянина',
      checkpoint: 'Блокпост',
      accident: 'ДТП',
      fire: 'Пожежа',
      protest: 'Протест',
      emergency: 'Надзвичайна подія',
      unknown: 'Невідомо'
    };
    return labels[type] || type;
  };
  
  const formatTime = (dateStr) => {
    if (!dateStr) return '—';
    const date = new Date(dateStr);
    return date.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit' }) + 
           ' ' + date.toLocaleDateString('uk-UA', { day: 'numeric', month: 'short' });
  };
  
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h2 className="text-2xl font-bold text-gray-900">Сигнали</h2>
        {selectedSignals.length > 0 && (
          <button
            onClick={handleBulkConfirm}
            className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white text-sm font-medium rounded-xl flex items-center gap-2"
          >
            <CheckCircle className="w-4 h-4" />
            Підтвердити ({selectedSignals.length})
          </button>
        )}
      </div>
      
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="glass-card p-4">
            <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
            <div className="text-sm text-gray-500">Всього 48г</div>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl font-bold text-orange-500">{stats.pending}</div>
            <div className="text-sm text-gray-500">На модерації</div>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl font-bold text-emerald-500">{stats.confirmed}</div>
            <div className="text-sm text-gray-500">Підтверджено</div>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl font-bold text-gray-400">{stats.raw}</div>
            <div className="text-sm text-gray-500">Необроблені</div>
          </div>
          <div className="glass-card p-4">
            <div className="text-2xl font-bold text-red-500">{stats.dismissed}</div>
            <div className="text-sm text-gray-500">Відхилено</div>
          </div>
        </div>
      )}
      
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Пошук сигналів..."
          className="flex-1 min-w-[200px] px-4 py-3 bg-white border border-gray-200 rounded-2xl text-gray-900 placeholder-gray-400 focus:outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-4 py-3 bg-white border border-gray-200 rounded-2xl text-gray-700 focus:outline-none focus:border-emerald-400 cursor-pointer"
        >
          <option value="">Всі статуси</option>
          <option value="raw">Необроблені</option>
          <option value="weak">Слабкі</option>
          <option value="medium">Середні</option>
          <option value="confirmed">Підтверджені</option>
          <option value="dismissed">Відхилені</option>
        </select>
        <select
          value={eventTypeFilter}
          onChange={(e) => setEventTypeFilter(e.target.value)}
          className="px-4 py-3 bg-white border border-gray-200 rounded-2xl text-gray-700 focus:outline-none focus:border-emerald-400 cursor-pointer"
        >
          <option value="">Всі типи</option>
          {eventTypes.map(type => (
            <option key={type} value={type}>{formatEventType(type)}</option>
          ))}
        </select>
        <button
          onClick={fetchSignals}
          className="px-4 py-3 bg-white border border-gray-200 rounded-2xl hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-5 h-5 text-gray-500" />
        </button>
      </div>
      
      {/* Signals Table */}
      <div className="glass-card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-32">
            <RefreshCw className="w-6 h-6 text-emerald-500 animate-spin" />
          </div>
        ) : signals.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Zap className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p>Сигналів не знайдено</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-100">
              <tr>
                <th className="px-4 py-4 text-left">
                  <input
                    type="checkbox"
                    checked={selectedSignals.length === signals.length && signals.length > 0}
                    onChange={() => setSelectedSignals(selectedSignals.length === signals.length ? [] : signals.map(s => s.signalId))}
                    className="rounded border-gray-300"
                  />
                </th>
                <th className="text-left px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Тип / Заголовок</th>
                <th className="text-left px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Статус</th>
                <th className="text-left px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Локація</th>
                <th className="text-left px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Джерело</th>
                <th className="text-left px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Час</th>
                <th className="text-right px-4 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Дії</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {signals.map((s) => (
                <tr key={s.signalId} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      checked={selectedSignals.includes(s.signalId)}
                      onChange={() => toggleSelect(s.signalId)}
                      className="rounded border-gray-300"
                    />
                  </td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-gray-900">{formatEventType(s.eventType)}</div>
                    <div className="text-sm text-gray-500 truncate max-w-[200px]">{s.title || s.description || '—'}</div>
                  </td>
                  <td className="px-4 py-4">{getStatusBadge(s.status, s.truthScore)}</td>
                  <td className="px-4 py-4">
                    {s.lat && s.lng ? (
                      <div className="flex items-center gap-1 text-sm text-gray-600">
                        <MapPin className="w-3 h-3 text-emerald-500" />
                        {s.lat.toFixed(4)}, {s.lng.toFixed(4)}
                      </div>
                    ) : (
                      <span className="text-gray-400">—</span>
                    )}
                    {s.address && <div className="text-xs text-gray-400 truncate max-w-[150px]">{s.address}</div>}
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-sm text-gray-600">{s.source || '—'}</div>
                    <div className="text-xs text-gray-400">{s.sourceType}</div>
                  </td>
                  <td className="px-4 py-4 text-sm text-gray-600">{formatTime(s.createdAt)}</td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-end gap-1">
                      {s.status !== 'confirmed' && s.status !== 'dismissed' && (
                        <>
                          <button
                            onClick={() => handleConfirm(s.signalId)}
                            className="p-2 hover:bg-emerald-50 rounded-lg transition-colors"
                            title="Підтвердити"
                          >
                            <CheckCircle className="w-4 h-4 text-emerald-500" />
                          </button>
                          <button
                            onClick={() => handleDismiss(s.signalId)}
                            className="p-2 hover:bg-red-50 rounded-lg transition-colors"
                            title="Відхилити"
                          >
                            <XCircle className="w-4 h-4 text-red-500" />
                          </button>
                        </>
                      )}
                      <button
                        onClick={() => handleDelete(s.signalId)}
                        className="p-2 hover:bg-red-50 rounded-lg transition-colors"
                        title="Видалити"
                      >
                        <Trash2 className="w-4 h-4 text-gray-400 hover:text-red-500" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ==================== Placeholders ====================
function PlaceholderView({ title, icon: Icon, description }) {
  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">{title}</h2>
      <div className="glass-card p-12 text-center">
        <Icon className="w-16 h-16 text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500 mb-2">{description}</p>
        <p className="text-sm text-gray-400">Буде доступно найближчим часом</p>
      </div>
    </div>
  );
}

// ==================== Main Component ====================
export default function GeoAdminPage() {
  const [token, setToken] = useState(() => localStorage.getItem('geo_admin_token'));
  const [activeNav, setActiveNav] = useState('dashboard');
  
  const handleLogout = () => {
    localStorage.removeItem('geo_admin_token');
    setToken(null);
  };
  
  if (!token) {
    return <AdminLogin onLogin={setToken} />;
  }
  
  const renderContent = () => {
    switch (activeNav) {
      case 'dashboard': return <DashboardView token={token} />;
      case 'revenue': return <RevenueView token={token} />;
      case 'signals': return <SignalsView token={token} />;
      case 'channels': return <ChannelsView token={token} />;
      case 'ai-engine': return <AIEngineView token={token} />;
      case 'sessions': return <SessionsView token={token} />;
      case 'users': return <UsersView token={token} />;
      case 'bot': return <BotView token={token} />;
      case 'analytics': return <PlaceholderView title="Аналітика" icon={BarChart3} description="Графіки та статистика" />;
      case 'logs': return <PlaceholderView title="Логи" icon={FileText} description="Системні логи" />;
      case 'settings': return <PlaceholderView title="Налаштування" icon={Settings} description="Конфігурація системи" />;
      default: return <DashboardView token={token} />;
    }
  };
  
  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shadow-sm">
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 bg-gradient-to-br from-emerald-400 to-teal-500 rounded-xl flex items-center justify-center shadow-lg">
              <Radio className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="font-bold text-gray-900">Geo Admin</h1>
              <p className="text-xs text-gray-500">Панель управління</p>
            </div>
          </div>
        </div>
        
        <nav className="flex-1 p-4 overflow-y-auto">
          <ul className="space-y-1">
            {NAV_ITEMS.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => setActiveNav(item.id)}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all font-medium ${
                    activeNav === item.id
                      ? 'bg-gradient-to-r from-emerald-50 to-teal-50 text-emerald-600 shadow-sm'
                      : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                  }`}
                >
                  <item.icon className={`w-5 h-5 ${activeNav === item.id ? 'text-emerald-500' : ''}`} />
                  {item.label}
                  {activeNav === item.id && <ChevronRight className="w-4 h-4 ml-auto text-emerald-400" />}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        
        <div className="p-4 border-t border-gray-100">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-3 text-red-500 hover:bg-red-50 rounded-xl transition-colors font-medium"
          >
            <LogOut className="w-5 h-5" />
            Вийти
          </button>
        </div>
      </aside>
      
      {/* Main content */}
      <main className="flex-1 p-8 overflow-auto">
        {renderContent()}
      </main>
    </div>
  );
}
