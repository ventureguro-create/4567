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
  
  // Fetch signals for map - NOW USING EVENTS (deduplicated)
  fetchSignals: async (days = 7) => {
    set({ signalsLoading: true });
    try {
      // Use events API for deduplicated/correlated signals
      const res = await fetch(`${API_BASE}/api/geo/events?days=${days}&limit=100`);
      const data = await res.json();
      if (data.ok) {
        // Transform event format to signal format for map compatibility
        const signals = (data.items || []).map(item => ({
          id: item.event_id,
          type: item.type || 'incident',
          lat: item.lat,
          lng: item.lng,
          confidence: item.confidence || 0.5,
          reports: item.report_count || 1,
          sources: item.source_count || 1,
          status: item.status,
          strength: item.strength || 'weak',
          createdAt: item.created_at,
          updatedAt: item.updated_at,
          expiresAt: item.expires_at,
          event_id: item.event_id, // Keep for event actions
          photo_count: item.photo_count || 0,
          user_confirmations: item.user_confirmations || 0,
          negative_reports: item.negative_reports || 0,
        }));
        set({ signals });
      }
    } catch (err) {
      console.error('Failed to fetch events:', err);
      // Fallback to old map API
      try {
        const res = await fetch(`${API_BASE}/api/geo/map?days=${days}&limit=50`);
        const data = await res.json();
        if (data.ok) {
          const signals = (data.items || []).map(item => ({
            ...item,
            type: mapEventType(item.eventType),
            confidence: 0.8,
          }));
          set({ signals });
        }
      } catch (fallbackErr) {
        console.error('Fallback fetch also failed:', fallbackErr);
      }
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
  
  // ==================== Event Builder API ====================
  
  // Events (deduplicated, correlated signals)
  events: [],
  eventsLoading: false,
  eventConfig: null,
  
  // Fetch events instead of raw signals
  fetchEvents: async (days = 7) => {
    set({ eventsLoading: true });
    try {
      const res = await fetch(`${API_BASE}/api/geo/events?days=${days}&limit=100`);
      const data = await res.json();
      if (data.ok) {
        set({ events: data.items || [] });
      }
    } catch (err) {
      console.error('Failed to fetch events:', err);
    } finally {
      set({ eventsLoading: false });
    }
  },
  
  // Confirm event (user sees it)
  confirmEvent: async (eventId) => {
    const { telegramUser, fetchEvents } = get();
    const userId = telegramUser?.id || 'anonymous';
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/events/${eventId}/confirm?userId=${userId}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.ok) {
        // Refresh events
        fetchEvents();
        return { success: true, data };
      }
      return { success: false, error: data.error };
    } catch (err) {
      console.error('Failed to confirm event:', err);
      return { success: false, error: err.message };
    }
  },
  
  // Report event not there
  reportNotThere: async (eventId) => {
    const { telegramUser, fetchEvents } = get();
    const userId = telegramUser?.id || 'anonymous';
    
    try {
      const res = await fetch(`${API_BASE}/api/geo/events/${eventId}/not-there?userId=${userId}`, {
        method: 'POST'
      });
      const data = await res.json();
      if (data.ok) {
        // Refresh events
        fetchEvents();
        return { success: true, data };
      }
      return { success: false, error: data.error };
    } catch (err) {
      console.error('Failed to report not-there:', err);
      return { success: false, error: err.message };
    }
  },
  
  // Get event details with reports
  getEventDetails: async (eventId) => {
    try {
      const res = await fetch(`${API_BASE}/api/geo/events/${eventId}`);
      const data = await res.json();
      return data;
    } catch (err) {
      console.error('Failed to get event details:', err);
      return { ok: false, error: err.message };
    }
  },
  
  // Fetch event builder config
  fetchEventConfig: async () => {
    try {
      const res = await fetch(`${API_BASE}/api/geo/events/config/info`);
      const data = await res.json();
      if (data.ok) {
        set({ eventConfig: data.config });
      }
    } catch (err) {
      console.error('Failed to fetch event config:', err);
    }
  },
}));
