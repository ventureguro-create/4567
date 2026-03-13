/**
 * Signal Freshness & TTL Decay
 * Signals fade over time and eventually disappear
 * 
 * Lifecycle:
 * - 0-10 min: FRESH (bright, pulsing)
 * - 10-30 min: RECENT (normal)
 * - 30-60 min: AGING (fading)
 * - 60+ min: OLD (very faded, may be filtered)
 * - 24h+: EXPIRED (should be removed)
 */

// TTL Configuration (in minutes)
export const TTL_CONFIG = {
  FRESH: 10,        // 0-10 min
  RECENT: 30,       // 10-30 min
  AGING: 60,        // 30-60 min
  OLD: 180,         // 1-3 hours
  EXPIRED: 1440,    // 24 hours
};

// Lifecycle stages
export const LIFECYCLE = {
  FRESH: 'fresh',
  RECENT: 'recent',
  AGING: 'aging',
  OLD: 'old',
  EXPIRED: 'expired',
};

/**
 * Calculate signal age in minutes
 */
export function getSignalAgeMinutes(createdAt) {
  if (!createdAt) return Infinity;
  
  const created = typeof createdAt === 'string' ? new Date(createdAt) : createdAt;
  const now = new Date();
  const diffMs = now - created;
  
  return Math.floor(diffMs / (1000 * 60));
}

/**
 * Get lifecycle stage based on age
 */
export function getLifecycleStage(createdAt) {
  const ageMinutes = getSignalAgeMinutes(createdAt);
  
  if (ageMinutes <= TTL_CONFIG.FRESH) return LIFECYCLE.FRESH;
  if (ageMinutes <= TTL_CONFIG.RECENT) return LIFECYCLE.RECENT;
  if (ageMinutes <= TTL_CONFIG.AGING) return LIFECYCLE.AGING;
  if (ageMinutes <= TTL_CONFIG.OLD) return LIFECYCLE.OLD;
  return LIFECYCLE.EXPIRED;
}

/**
 * Get opacity based on signal age (decay effect)
 * Fresh = 1.0, fades to 0.3 over time
 */
export function getDecayOpacity(createdAt) {
  const ageMinutes = getSignalAgeMinutes(createdAt);
  
  if (ageMinutes <= TTL_CONFIG.FRESH) {
    return 1.0; // Full brightness
  }
  
  if (ageMinutes <= TTL_CONFIG.RECENT) {
    // Linear decay from 1.0 to 0.8
    const progress = (ageMinutes - TTL_CONFIG.FRESH) / (TTL_CONFIG.RECENT - TTL_CONFIG.FRESH);
    return 1.0 - (progress * 0.2);
  }
  
  if (ageMinutes <= TTL_CONFIG.AGING) {
    // Linear decay from 0.8 to 0.5
    const progress = (ageMinutes - TTL_CONFIG.RECENT) / (TTL_CONFIG.AGING - TTL_CONFIG.RECENT);
    return 0.8 - (progress * 0.3);
  }
  
  if (ageMinutes <= TTL_CONFIG.OLD) {
    // Linear decay from 0.5 to 0.3
    const progress = (ageMinutes - TTL_CONFIG.AGING) / (TTL_CONFIG.OLD - TTL_CONFIG.AGING);
    return 0.5 - (progress * 0.2);
  }
  
  // Very old signals
  return 0.25;
}

/**
 * Get scale factor for marker (fresh signals are slightly larger)
 */
export function getDecayScale(createdAt) {
  const stage = getLifecycleStage(createdAt);
  
  switch (stage) {
    case LIFECYCLE.FRESH: return 1.1;
    case LIFECYCLE.RECENT: return 1.0;
    case LIFECYCLE.AGING: return 0.9;
    case LIFECYCLE.OLD: return 0.85;
    default: return 0.8;
  }
}

/**
 * Check if signal should show pulse animation (only fresh)
 */
export function shouldPulse(createdAt) {
  return getLifecycleStage(createdAt) === LIFECYCLE.FRESH;
}

/**
 * Check if signal is expired and should be filtered out
 */
export function isExpired(createdAt) {
  return getLifecycleStage(createdAt) === LIFECYCLE.EXPIRED;
}

/**
 * Filter out expired signals
 */
export function filterActiveSignals(signals) {
  return signals.filter(s => !isExpired(s.createdAt || s.created_at));
}

/**
 * Get human-readable time ago string
 */
export function getTimeAgo(createdAt) {
  const ageMinutes = getSignalAgeMinutes(createdAt);
  
  if (ageMinutes < 1) return 'щойно';
  if (ageMinutes < 60) return `${ageMinutes} хв`;
  
  const hours = Math.floor(ageMinutes / 60);
  if (hours < 24) return `${hours} год`;
  
  const days = Math.floor(hours / 24);
  return `${days} дн`;
}

/**
 * Get color modifier based on freshness
 * Fresh signals have more saturated colors
 */
export function getColorWithDecay(baseColor, createdAt) {
  const opacity = getDecayOpacity(createdAt);
  
  // Parse hex color
  const hex = baseColor.replace('#', '');
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  
  // Blend with white based on decay (fading effect)
  const fade = 1 - opacity;
  const newR = Math.round(r + (255 - r) * fade * 0.5);
  const newG = Math.round(g + (255 - g) * fade * 0.5);
  const newB = Math.round(b + (255 - b) * fade * 0.5);
  
  return `rgba(${newR}, ${newG}, ${newB}, ${opacity})`;
}

/**
 * Get lifecycle badge info for UI
 */
export function getLifecycleBadge(createdAt) {
  const stage = getLifecycleStage(createdAt);
  const timeAgo = getTimeAgo(createdAt);
  
  switch (stage) {
    case LIFECYCLE.FRESH:
      return {
        label: timeAgo,
        color: '#22C55E',
        bgColor: '#22C55E20',
        pulse: true,
      };
    case LIFECYCLE.RECENT:
      return {
        label: timeAgo,
        color: '#3B82F6',
        bgColor: '#3B82F620',
        pulse: false,
      };
    case LIFECYCLE.AGING:
      return {
        label: timeAgo,
        color: '#F59E0B',
        bgColor: '#F59E0B20',
        pulse: false,
      };
    case LIFECYCLE.OLD:
      return {
        label: timeAgo,
        color: '#94A3B8',
        bgColor: '#94A3B820',
        pulse: false,
      };
    default:
      return {
        label: timeAgo,
        color: '#64748B',
        bgColor: '#64748B20',
        pulse: false,
      };
  }
}
