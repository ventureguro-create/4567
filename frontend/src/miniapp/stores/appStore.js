/**
 * Global app store using Zustand
 */
import { create } from 'zustand';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// Map backend eventType to frontend type
function mapEventType(eventType) {
  const mapping = {
    'police': 'police',
    'virus': 'virus',
    'rain': 'weather',
    'heavy_rain': 'weather',
    'weather': 'weather',
    'trash': 'trash',
    'danger': 'danger',
    'fire': 'incident',
    'incident': 'incident',
  };
  return mapping[eventType] || 'danger';
}

export const useAppStore = create((set, get) => ({
  // User state
  user: null,
  telegramUser: null,
  isAuthenticated: false,
  
  // Location state
  userLocation: null,
  locationError: null,
  
  // Radar state
  radarActive: false,
  radarRadius: 1000,
  
  // Signals
  signals: [],
  nearbySignals: [],
  signalsLoading: false,
  
  // Alerts
  alerts: [],
  alertsLoading: false,
  unreadAlerts: 0,
  
  // UI state
  activeTab: 'radar',
  
  // Actions
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setTelegramUser: (telegramUser) => set({ telegramUser }),
  
  setUserLocation: (location) => set({ 
    userLocation: location,
    locationError: null 
  }),
  
  setLocationError: (error) => set({ locationError: error }),
  
  setRadarActive: (active) => set({ radarActive: active }),
  setRadarRadius: (radius) => set({ radarRadius: radius }),
  
  setActiveTab: (tab) => set({ activeTab: tab }),
  
  // Fetch signals for map
  fetchSignals: async (days = 7) => {
    set({ signalsLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/geo/map?days=${days}&limit=50`);
      const data = await res.json();
      if (data.ok) {
        // Transform eventType to type for compatibility
        const signals = (data.items || []).map(item => ({
          ...item,
          type: mapEventType(item.eventType),
          confidence: 0.8, // Default confidence
        }));
        set({ signals });
      }
    } catch (err) {
      console.error('Failed to fetch signals:', err);
    } finally {
      set({ signalsLoading: false });
    }
  },
  
  // Fetch nearby signals (radar mode)
  fetchNearbySignals: async () => {
    const { userLocation, radarRadius } = get();
    // Use default Kyiv location if not available
    const location = userLocation || { lat: 50.4501, lng: 30.5234 };
    
    set({ signalsLoading: true });
    try {
      // Use map endpoint with distance filter
      const res = await fetch(
        `${API_BASE}/api/geo/map?limit=100`
      );
      const data = await res.json();
      if (data.ok) {
        // Filter by distance and transform
        const nearby = (data.items || [])
          .map(item => ({
            ...item,
            type: mapEventType(item.eventType),
            confidence: 0.8,
          }))
          .filter(item => {
            // Calculate distance
            const R = 6371000;
            const dLat = (item.lat - location.lat) * Math.PI / 180;
            const dLon = (item.lng - location.lng) * Math.PI / 180;
            const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
                      Math.cos(location.lat * Math.PI / 180) * Math.cos(item.lat * Math.PI / 180) *
                      Math.sin(dLon/2) * Math.sin(dLon/2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
            const d = R * c;
            return d <= radarRadius;
          });
        set({ nearbySignals: nearby });
      }
    } catch (err) {
      console.error('Failed to fetch nearby signals:', err);
    } finally {
      set({ signalsLoading: false });
    }
  },
  
  // Report a new signal
  reportSignal: async (type, location, description = '', photo = null) => {
    const { telegramUser } = get();
    
    try {
      const body = {
        type,
        lat: location.lat,
        lng: location.lng,
        description,
        source: 'miniapp',
        userId: telegramUser?.id || null,
        username: telegramUser?.username || null,
      };
      
      const res = await fetch(`${API_BASE}/api/geo/miniapp/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      
      const data = await res.json();
      return data;
    } catch (err) {
      console.error('Failed to report signal:', err);
      return { ok: false, error: err.message };
    }
  },
  
  // Confirm/reject a signal
  voteSignal: async (signalId, vote) => {
    const { telegramUser } = get();
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/signal/${signalId}/vote`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          vote, // 'confirm' or 'reject'
          userId: telegramUser?.id || null,
        })
      });
      
      const data = await res.json();
      return data;
    } catch (err) {
      console.error('Failed to vote signal:', err);
      return { ok: false, error: err.message };
    }
  },
  
  // Fetch user profile
  fetchProfile: async () => {
    const { telegramUser } = get();
    if (!telegramUser?.id) return;
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/user/${telegramUser.id}/profile`);
      const data = await res.json();
      if (data.ok) {
        set({ user: data.user });
      }
    } catch (err) {
      console.error('Failed to fetch profile:', err);
    }
  },
  
  // Fetch alerts
  fetchAlerts: async () => {
    const { telegramUser } = get();
    if (!telegramUser?.id) return;
    
    set({ alertsLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/geo/miniapp/user/${telegramUser.id}/alerts`);
      const data = await res.json();
      if (data.ok) {
        set({ 
          alerts: data.items || [],
          unreadAlerts: data.unread || 0
        });
      }
    } catch (err) {
      console.error('Failed to fetch alerts:', err);
    } finally {
      set({ alertsLoading: false });
    }
  },
}));
