/**
 * AI Risk Zone Analysis - Refactored per HeatMap Specification
 * 
 * Heatmap Architecture:
 * 1. Base Map Layer
 * 2. Heatmap Layer (soft background)
 * 3. Signal Markers Layer (icons)
 * 4. Radar Layer (user GPS pulse)
 * 
 * Key Principles:
 * - Heatmap is SECONDARY, not primary
 * - Only shows when signals >= 3 in radius
 * - Uses weighted points: severity * confidence * freshness
 * - Low opacity (0.18-0.28), small radius (18-28), blur (14-22)
 */

// Severity weights per signal type (from specification)
const SEVERITY_MAP = {
  police: 0.5,
  checkpoint: 0.6,
  trash: 0.4,
  weather: 0.5,
  toxic_cloud: 0.8,
  virus: 0.9,
  danger: 0.95,
  incident: 0.85,
  zombie: 0.9,
  zombie_trash: 1.0,
};

// Calculate distance between two points in meters
export function calculateDistance(lat1, lng1, lat2, lng2) {
  const R = 6371000; // Earth radius in meters
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2) * Math.sin(dLat/2) +
            Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
            Math.sin(dLng/2) * Math.sin(dLng/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  return R * c;
}

/**
 * Calculate freshness factor based on signal age
 * 0-10 min = 1.0
 * 10-30 min = 0.7
 * 30-60 min = 0.4
 * 60+ min = 0.15
 */
export function calculateFreshness(createdAt) {
  if (!createdAt) return 0.5;
  
  const now = Date.now();
  const created = new Date(createdAt).getTime();
  const minutesAgo = (now - created) / 60000;
  
  if (minutesAgo <= 10) return 1.0;
  if (minutesAgo <= 30) return 0.7;
  if (minutesAgo <= 60) return 0.4;
  return 0.15;
}

/**
 * Calculate weight for a single signal (heatmap intensity)
 * Formula: weight = severity * confidence * freshness
 */
export function getSignalWeight(signal) {
  const severity = SEVERITY_MAP[signal.type] || 0.5;
  const confidence = signal.confidence ?? 0.7;
  const freshness = calculateFreshness(signal.createdAt || signal.created_at);
  
  return severity * confidence * freshness;
}

/**
 * Filter signals for heatmap display
 * Only include: active, fresh, geo-valid signals
 */
export function filterSignalsForHeatmap(signals, userLocation, radarRadius) {
  if (!signals || signals.length === 0) return [];
  
  return signals.filter(signal => {
    // Must have valid coordinates
    if (!signal.lat || !signal.lng) return false;
    
    // Must be active (not archived/declined)
    if (signal.status === 'archived' || signal.status === 'declined') return false;
    
    // If we have user location and radius, filter by distance
    if (userLocation && radarRadius) {
      const distance = calculateDistance(
        userLocation.lat, userLocation.lng,
        signal.lat, signal.lng
      );
      if (distance > radarRadius) return false;
    }
    
    return true;
  });
}

/**
 * Generate heatmap points with proper weighting
 * Returns array of {lat, lng, intensity} for heatmap layer
 * 
 * IMPORTANT: Only call this when signals.length >= 3
 */
export function generateHeatmapPoints(signals) {
  if (!signals || signals.length < 3) {
    return []; // No heatmap for < 3 signals
  }
  
  return signals.map(signal => {
    const weight = getSignalWeight(signal);
    
    return {
      lat: signal.lat,
      lng: signal.lng,
      // Scale intensity to be subtle (max ~0.8 instead of full 1.0)
      intensity: Math.min(0.8, weight),
    };
  });
}

/**
 * Check if heatmap should be displayed
 * Rule: Show heatmap only when signals >= 3
 */
export function shouldShowHeatmap(signals) {
  return signals && signals.length >= 3;
}

/**
 * Get heatmap configuration based on signal count
 * Returns optimized settings per specification:
 * - radius: 18-28
 * - blur: 14-22  
 * - opacity: 0.18-0.28 (max 0.32)
 * 
 * CRITICAL: Heatmap must be VERY subtle - almost invisible background
 */
export function getHeatmapConfig(signalCount) {
  // Base config - EXTREMELY subtle, barely visible
  const config = {
    radius: 15,     // Small radius to avoid spreading
    blur: 20,       // High blur for softness
    maxZoom: 17,
    minOpacity: 0.05,  // Very low base opacity
    max: 2.5,       // High max = lower intensity per point
  };
  
  // For more signals - even MORE subtle
  if (signalCount >= 10) {
    config.radius = 12;
    config.blur = 25;
    config.max = 3.5;  // Even lower intensity
  } else if (signalCount >= 5) {
    config.radius = 14;
    config.blur = 22;
    config.max = 3.0;
  }
  
  return config;
}

// Cluster signals within a radius (for risk zone analysis)
export function clusterSignals(signals, clusterRadius = 200) {
  const clusters = [];
  const used = new Set();
  
  signals.forEach((signal, i) => {
    if (used.has(i)) return;
    
    const cluster = {
      center: { lat: signal.lat, lng: signal.lng },
      signals: [signal],
      totalSeverity: getSignalWeight(signal),
    };
    
    signals.forEach((other, j) => {
      if (i === j || used.has(j)) return;
      
      const dist = calculateDistance(signal.lat, signal.lng, other.lat, other.lng);
      if (dist <= clusterRadius) {
        cluster.signals.push(other);
        cluster.totalSeverity += getSignalWeight(other);
        used.add(j);
      }
    });
    
    // Recalculate center as centroid
    if (cluster.signals.length > 1) {
      const sumLat = cluster.signals.reduce((sum, s) => sum + s.lat, 0);
      const sumLng = cluster.signals.reduce((sum, s) => sum + s.lng, 0);
      cluster.center = {
        lat: sumLat / cluster.signals.length,
        lng: sumLng / cluster.signals.length,
      };
    }
    
    used.add(i);
    clusters.push(cluster);
  });
  
  return clusters;
}

// Analyze risk zones based on signal clusters
export function analyzeRiskZones(signals) {
  if (!signals || signals.length === 0) {
    return { zones: [], alerts: [], overallRisk: 'low' };
  }
  
  const clusters = clusterSignals(signals, 300); // 300m cluster radius
  const zones = [];
  const alerts = [];
  
  clusters.forEach(cluster => {
    const signalCount = cluster.signals.length;
    const avgWeight = cluster.totalSeverity / signalCount;
    
    // Calculate risk score
    let riskScore = 0;
    
    // Factor 1: Number of signals (more signals = higher risk)
    if (signalCount >= 5) riskScore += 0.4;
    else if (signalCount >= 3) riskScore += 0.25;
    else if (signalCount >= 2) riskScore += 0.1;
    
    // Factor 2: Average weight (severity * confidence * freshness)
    riskScore += avgWeight * 0.4;
    
    // Factor 3: Signal types (danger/virus = high priority)
    const hasDanger = cluster.signals.some(s => s.type === 'danger' || s.type === 'virus');
    if (hasDanger) riskScore += 0.2;
    
    // Determine risk level
    let riskLevel = 'safe';
    if (riskScore >= 0.7) riskLevel = 'danger';
    else if (riskScore >= 0.4) riskLevel = 'warning';
    
    const zone = {
      center: cluster.center,
      radius: Math.max(200, signalCount * 50), // Dynamic radius
      riskLevel,
      riskScore,
      signalCount,
      signals: cluster.signals,
    };
    
    zones.push(zone);
    
    // Generate alerts for high-risk zones
    if (riskLevel === 'danger') {
      alerts.push({
        type: 'danger_zone',
        message: `Зона підвищеної небезпеки: ${signalCount} сигналів`,
        center: cluster.center,
        severity: 'high',
      });
    } else if (riskLevel === 'warning' && signalCount >= 3) {
      alerts.push({
        type: 'warning_zone',
        message: `Увага: ${signalCount} сигналів поруч`,
        center: cluster.center,
        severity: 'medium',
      });
    }
  });
  
  // Calculate overall risk
  const dangerZones = zones.filter(z => z.riskLevel === 'danger').length;
  const warningZones = zones.filter(z => z.riskLevel === 'warning').length;
  
  let overallRisk = 'low';
  if (dangerZones >= 2) overallRisk = 'critical';
  else if (dangerZones >= 1) overallRisk = 'high';
  else if (warningZones >= 2) overallRisk = 'medium';
  
  return { zones, alerts, overallRisk };
}

// Get risk color based on level
export function getRiskColor(riskLevel) {
  switch (riskLevel) {
    case 'danger': return '#EF4444';
    case 'warning': return '#F59E0B';
    case 'safe': return '#22C55E';
    default: return '#64748B';
  }
}

// Get risk zone opacity (kept low per spec)
export function getRiskOpacity(riskScore) {
  // Max 0.32 per specification
  return Math.min(0.32, 0.08 + riskScore * 0.24);
}
