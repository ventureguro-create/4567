/**
 * Radar Page - Urban Intelligence System
 * 
 * ARCHITECTURE:
 * - MAP = APPLICATION (fullscreen background)
 * - Minimal dot markers (8-14px) with pulse animation
 * - Signal levels: weak → medium → strong
 * - Clustering for zoom < 12
 * - Signal card popup on click
 * 
 * LAYER ORDER:
 * 1. Base Map (fullscreen)
 * 2. Heatmap (soft background, >= 3 signals)
 * 3. Signal Markers (minimal dots)
 * 4. Radar Sweep (canvas animation)
 * 5. UI Overlays (floating)
 */
import { useEffect, useCallback, useState, useRef, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Circle, useMap, useMapEvents, Popup } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { HeatmapLayer } from 'react-leaflet-heatmap-layer-v3';
import { Radio, Navigation, RefreshCw, X, AlertTriangle, Clock, Flame, Plus, Check, XCircle, MapPin } from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { requestLocation, vibrate } from '../lib/telegram';
import { SIGNAL_TYPES, getSignalSeverity } from '../lib/signalTypes';
import { 
  analyzeRiskZones, 
  generateHeatmapPoints, 
  getRiskColor, 
  getRiskOpacity,
  shouldShowHeatmap,
  getHeatmapConfig,
  filterSignalsForHeatmap,
  calculateDistance
} from '../lib/riskAnalysis';
import { 
  getDecayOpacity, 
  filterActiveSignals, 
  getLifecycleBadge,
  getTimeAgo,
  LIFECYCLE,
  getLifecycleStage
} from '../lib/signalDecay';
import SignalToast from '../components/SignalToast';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Signal colors by type
const SIGNAL_COLORS = {
  virus: '#22c55e',      // green
  danger: '#ef4444',     // red
  police: '#ef4444',     // red
  trash: '#9ca3af',      // gray
  weather: '#3b82f6',    // blue
  incident: '#f59e0b',   // amber
  checkpoint: '#8b5cf6', // purple
  toxic_cloud: '#f97316', // orange
  zombie: '#dc2626',     // dark red
  zombie_trash: '#7c3aed', // violet
};

// Glow colors based on confidence level
const GLOW_COLORS = {
  weak: 'rgba(156, 163, 175, 0.4)',    // gray glow
  medium: 'rgba(234, 179, 8, 0.5)',    // yellow glow
  strong: 'rgba(239, 68, 68, 0.6)',    // red glow
};

// Get signal strength level based on confidence and reports
function getSignalStrength(signal) {
  const confidence = signal.confidence || 0.5;
  const reports = signal.reports || 1;
  
  if (confidence >= 0.8 || reports >= 5) return 'strong';
  if (confidence >= 0.5 || reports >= 3) return 'medium';
  return 'weak';
}

// Icon paths mapping
const ICON_PATHS = {
  virus: '/icons/virus.png',
  danger: '/icons/danger.png',
  police: '/icons/police.png',
  trash: '/icons/trash.png',
  weather: '/icons/weather.png',
  incident: '/icons/incident.png',
};

// Create icon marker - CLEAN with contrast shadow
function createIconMarker(signal, mapZoom = 14) {
  const type = signal.type || 'incident';
  const lifecycle = getLifecycleStage(signal.createdAt || signal.created_at);
  const opacity = getDecayOpacity(signal.createdAt || signal.created_at);
  
  // Zoom-based scaling: bigger icons at higher zoom
  let iconSize;
  if (mapZoom < 12) {
    iconSize = 28;
  } else if (mapZoom < 14) {
    iconSize = 36;
  } else if (mapZoom < 16) {
    iconSize = 44;
  } else {
    iconSize = 52;
  }
  
  // Pulse animation only for fresh signals
  const showPulse = lifecycle === LIFECYCLE.FRESH;
  
  // Get icon path
  const iconPath = ICON_PATHS[type] || ICON_PATHS.incident;
  
  return L.divIcon({
    className: 'signal-icon-wrapper',
    html: `
      <div class="signal-icon-container" style="opacity: ${opacity};">
        <img 
          src="${iconPath}" 
          alt="${type}"
          class="signal-icon-img ${showPulse ? 'pulse-active' : ''}"
          style="
            width: ${iconSize}px; 
            height: ${iconSize}px;
            filter: drop-shadow(0 2px 3px rgba(0,0,0,0.35)) drop-shadow(0 0 1px rgba(0,0,0,0.2));
          "
        />
      </div>
    `,
    iconSize: [iconSize, iconSize],
    iconAnchor: [iconSize / 2, iconSize / 2],
    popupAnchor: [0, -iconSize],
  });
}

// User location marker
const userLocationIcon = L.divIcon({
  className: 'user-location-wrapper',
  html: `
    <div class="user-location-marker">
      <div class="user-location-pulse"></div>
      <div class="user-location-dot"></div>
    </div>
  `,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

// Cluster icon
function createClusterIcon(cluster) {
  const count = cluster.getChildCount();
  const size = count < 10 ? 32 : count < 50 ? 40 : 48;
  
  return L.divIcon({
    html: `
      <div class="signal-cluster" style="width: ${size}px; height: ${size}px;">
        <span>${count}</span>
      </div>
    `,
    className: 'signal-cluster-wrapper',
    iconSize: [size, size],
  });
}

// Map controller
function MapController({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) {
      map.setView(center, zoom || 14, { animate: true, duration: 0.5 });
    }
  }, [center, zoom, map]);
  return null;
}

// Radar Sweep Animation (Canvas)
function RadarSweepLayer({ center, radius, active }) {
  const map = useMap();
  const canvasRef = useRef(null);
  const animationRef = useRef(null);
  
  useEffect(() => {
    if (!active || !center) return;
    
    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;z-index:450;';
    
    const container = map.getContainer();
    container.appendChild(canvas);
    canvasRef.current = canvas;
    
    const ctx = canvas.getContext('2d');
    let rotation = 0;
    
    const resize = () => {
      canvas.width = container.clientWidth;
      canvas.height = container.clientHeight;
    };
    resize();
    
    const animate = () => {
      if (!canvasRef.current) return;
      
      const width = canvas.width;
      const height = canvas.height;
      const centerPoint = map.latLngToContainerPoint(center);
      const cx = centerPoint.x;
      const cy = centerPoint.y;
      
      const metersPerPixel = 40075016.686 * Math.cos(center[0] * Math.PI / 180) / Math.pow(2, map.getZoom() + 8);
      const pixelRadius = radius / metersPerPixel;
      
      ctx.clearRect(0, 0, width, height);
      
      // Draw sweep sector
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(rotation * Math.PI / 180);
      
      const gradient = ctx.createLinearGradient(0, 0, 0, -pixelRadius);
      gradient.addColorStop(0, 'rgba(59, 130, 246, 0.4)');
      gradient.addColorStop(0.5, 'rgba(59, 130, 246, 0.15)');
      gradient.addColorStop(1, 'rgba(59, 130, 246, 0)');
      
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.arc(0, 0, pixelRadius, -Math.PI/2 - Math.PI/6, -Math.PI/2);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();
      
      // Sweep line
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(0, -pixelRadius);
      ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
      ctx.lineWidth = 1.5;
      ctx.stroke();
      
      ctx.restore();
      
      // Pulse rings (every 10 sec effect)
      const time = Date.now() / 1000;
      for (let i = 0; i < 2; i++) {
        const phase = (time + i * 1.5) % 3;
        const ringRadius = (phase / 3) * pixelRadius;
        const opacity = 1 - phase / 3;
        
        ctx.beginPath();
        ctx.arc(cx, cy, ringRadius, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(59, 130, 246, ${opacity * 0.3})`;
        ctx.lineWidth = 1;
        ctx.stroke();
      }
      
      rotation = (rotation + 1.2) % 360;
      animationRef.current = requestAnimationFrame(animate);
    };
    
    animate();
    
    const updateCanvas = () => resize();
    map.on('move', updateCanvas);
    map.on('zoom', updateCanvas);
    map.on('resize', resize);
    
    return () => {
      if (animationRef.current) cancelAnimationFrame(animationRef.current);
      if (canvasRef.current && container.contains(canvasRef.current)) {
        container.removeChild(canvasRef.current);
      }
      map.off('move', updateCanvas);
      map.off('zoom', updateCanvas);
      map.off('resize', resize);
    };
  }, [map, center, radius, active]);
  
  return null;
}

// Signal Card Component - ICON ONLY (no text labels)
function SignalCard({ signal, userLocation, onConfirm, onDismiss, onClose }) {
  const signalType = SIGNAL_TYPES.find(t => t.id === signal.type) || SIGNAL_TYPES[0];
  const lifecycle = getLifecycleBadge(signal.createdAt || signal.created_at);
  const timeAgo = getTimeAgo(signal.createdAt || signal.created_at);
  const strength = getSignalStrength(signal);
  const color = SIGNAL_COLORS[signal.type] || '#64748b';
  const confirmations = signal.confirmations || 0;
  const confidence = Math.round((signal.confidence || 0.5) * 100);
  
  // Calculate distance
  let distance = null;
  let distanceM = null;
  if (userLocation && signal.lat && signal.lng) {
    distanceM = calculateDistance(userLocation.lat, userLocation.lng, signal.lat, signal.lng);
    distance = distanceM < 1000 ? `${Math.round(distanceM)}м` : `${(distanceM/1000).toFixed(1)}км`;
  }
  
  // Open route in Google Maps (avoid this location)
  const handleAvoidRoute = (mode) => {
    if (!userLocation || !signal.lat || !signal.lng) return;
    
    // Calculate a point to avoid (slightly past the signal)
    const avoidLat = signal.lat;
    const avoidLng = signal.lng;
    
    // Destination: a point beyond the signal (user's general direction)
    // For demo, we just open directions avoiding this waypoint
    const travelMode = mode === 'walk' ? 'walking' : 'driving';
    
    // Google Maps URL with waypoint to avoid
    // Using directions from current location, avoiding the signal area
    const destLat = signal.lat + (signal.lat - userLocation.lat) * 0.5;
    const destLng = signal.lng + (signal.lng - userLocation.lng) * 0.5;
    
    const url = `https://www.google.com/maps/dir/?api=1&origin=${userLocation.lat},${userLocation.lng}&destination=${destLat.toFixed(6)},${destLng.toFixed(6)}&travelmode=${travelMode}&avoid=tolls`;
    
    window.open(url, '_blank');
  };
  
  return (
    <div className="signal-card-popup" data-testid="signal-card">
      <button onClick={onClose} className="signal-card-close">
        <X size={16} />
      </button>
      
      {/* Icon Only Header - NO TEXT LABEL */}
      <div className="signal-card-icon-header">
        <img 
          src={signalType.iconPath || `/icons/${signal.type}.png`}
          alt=""
          className="signal-card-main-icon"
        />
        <span 
          className="signal-card-lifecycle-badge"
          style={{ background: lifecycle.bgColor, color: lifecycle.color }}
        >
          {lifecycle.label}
        </span>
      </div>
      
      {/* Stats Row - Distance, Time, Confidence */}
      <div className="signal-card-stats">
        {distance && (
          <div className="signal-stat">
            <span className="signal-stat-value">{distance}</span>
          </div>
        )}
        <div className="signal-stat">
          <Clock size={12} />
          <span className="signal-stat-value">{timeAgo}</span>
        </div>
        <div className="signal-stat">
          <span className="signal-stat-value confidence">{confidence}%</span>
        </div>
      </div>
      
      {/* Confirmation indicator */}
      {confirmations > 0 && (
        <div className="signal-confirmations">
          <span className="confirmation-count">{confirmations}</span>
          <span className="confirmation-label">підтвердили</span>
        </div>
      )}
      
      {/* Strength dots */}
      <div className="signal-card-strength">
        <div className="signal-strength-dots">
          <div className={`strength-dot ${strength === 'weak' || strength === 'medium' || strength === 'strong' ? 'active' : ''}`} style={{ background: color }} />
          <div className={`strength-dot ${strength === 'medium' || strength === 'strong' ? 'active' : ''}`} style={{ background: color }} />
          <div className={`strength-dot ${strength === 'strong' ? 'active' : ''}`} style={{ background: color }} />
        </div>
      </div>
      
      {/* Route Buttons - Avoid Signal */}
      <div className="signal-card-route-actions">
        <button 
          onClick={() => handleAvoidRoute('walk')} 
          className="signal-route-btn walk"
          data-testid="route-walk"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="5" r="2"/>
            <path d="M10 22V18L8 13L10 9H14L16 13L14 18V22"/>
          </svg>
          Обійти пішки
        </button>
        <button 
          onClick={() => handleAvoidRoute('drive')} 
          className="signal-route-btn drive"
          data-testid="route-drive"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 17h14v-6l-2-6H7l-2 6v6zM5 17v2h3v-2M16 17v2h3v-2"/>
            <circle cx="7.5" cy="14.5" r="1.5"/>
            <circle cx="16.5" cy="14.5" r="1.5"/>
          </svg>
          Об'їхати
        </button>
      </div>
      
      {/* Action Buttons - Confirm / Not There */}
      <div className="signal-card-actions">
        <button onClick={onConfirm} className="signal-action-btn confirm" data-testid="confirm-signal">
          <Check size={16} />
          Ще там
        </button>
        <button onClick={onDismiss} className="signal-action-btn dismiss" data-testid="dismiss-signal">
          <XCircle size={16} />
          Вже немає
        </button>
      </div>
    </div>
  );
}

export default function RadarPage() {
  const {
    userLocation,
    setUserLocation,
    setLocationError,
    radarActive,
    setRadarActive,
    radarRadius,
    setRadarRadius,
    signals,
    nearbySignals,
    signalsLoading,
    fetchSignals,
    fetchNearbySignals,
    setActiveTab,
  } = useAppStore();
  
  const [locating, setLocating] = useState(false);
  const [mapCenter, setMapCenter] = useState([50.4501, 30.5234]);
  const [toastSignal, setToastSignal] = useState(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [riskAlert, setRiskAlert] = useState(null);
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [mapZoom, setMapZoom] = useState(14);
  const lastToastRef = useRef(null);
  
  // Filter active signals
  const activeSignals = useMemo(() => {
    const signalsToFilter = radarActive ? nearbySignals : signals;
    return filterActiveSignals(signalsToFilter);
  }, [signals, nearbySignals, radarActive]);
  
  // Heatmap signals
  const heatmapSignals = useMemo(() => {
    return filterSignalsForHeatmap(activeSignals, userLocation, radarActive ? radarRadius : null);
  }, [activeSignals, userLocation, radarActive, radarRadius]);
  
  // Risk analysis
  const riskAnalysis = useMemo(() => {
    const signalsWithSeverity = activeSignals.map(s => ({
      ...s,
      severity: getSignalSeverity(s.type),
    }));
    return analyzeRiskZones(signalsWithSeverity);
  }, [activeSignals]);
  
  // Heatmap config
  const heatmapPoints = useMemo(() => {
    if (!shouldShowHeatmap(heatmapSignals)) return [];
    return generateHeatmapPoints(heatmapSignals);
  }, [heatmapSignals]);
  
  const heatmapConfig = useMemo(() => getHeatmapConfig(heatmapSignals.length), [heatmapSignals.length]);
  const displayHeatmap = showHeatmap && shouldShowHeatmap(heatmapSignals);
  
  // Count stats
  const freshCount = useMemo(() => {
    return activeSignals.filter(s => 
      getLifecycleStage(s.createdAt || s.created_at) === LIFECYCLE.FRESH
    ).length;
  }, [activeSignals]);
  
  // Track zoom for clustering
  function ZoomTracker() {
    const map = useMapEvents({
      zoomend: () => setMapZoom(map.getZoom()),
    });
    return null;
  }
  
  // Alert effect
  useEffect(() => {
    if (riskAnalysis.alerts.length > 0 && radarActive) {
      const highAlert = riskAnalysis.alerts.find(a => a.severity === 'high');
      if (highAlert) {
        setRiskAlert(highAlert);
        vibrate('error');
        setTimeout(() => setRiskAlert(null), 5000);
      }
    }
  }, [riskAnalysis.alerts, radarActive]);
  
  // Get location
  const getLocation = useCallback(async () => {
    setLocating(true);
    try {
      const location = await requestLocation();
      setUserLocation(location);
      setMapCenter([location.lat, location.lng]);
      vibrate('success');
    } catch (err) {
      setLocationError(err.message);
      vibrate('error');
    } finally {
      setLocating(false);
    }
  }, [setUserLocation, setLocationError]);
  
  useEffect(() => {
    fetchSignals();
    getLocation();
  }, [fetchSignals, getLocation]);
  
  useEffect(() => {
    if (radarActive) {
      fetchNearbySignals();
      // Live pulse - fetch every 10 seconds when radar is active
      const interval = setInterval(fetchNearbySignals, 10000);
      return () => clearInterval(interval);
    }
  }, [radarActive, radarRadius, fetchNearbySignals]);
  
  // Background pulse for all signals - every 12 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!radarActive) {
        fetchSignals();
      }
    }, 12000);
    return () => clearInterval(interval);
  }, [radarActive, fetchSignals]);
  
  // Toast for new signals
  useEffect(() => {
    if (radarActive && nearbySignals.length > 0) {
      const latestSignal = nearbySignals[0];
      const signalId = latestSignal.id || latestSignal._id;
      
      if (lastToastRef.current !== signalId) {
        lastToastRef.current = signalId;
        
        if (userLocation) {
          const dist = calculateDistance(userLocation.lat, userLocation.lng, latestSignal.lat, latestSignal.lng);
          latestSignal.distance = dist < 1000 ? `${Math.round(dist)}м` : `${(dist/1000).toFixed(1)}км`;
        }
        
        setToastSignal(latestSignal);
        vibrate('medium');
      }
    }
  }, [nearbySignals, radarActive, userLocation]);
  
  const toggleRadar = () => {
    vibrate('medium');
    setRadarActive(!radarActive);
  };
  
  const handleSignalClick = (signal) => {
    setSelectedSignal(signal);
    vibrate('light');
  };
  
  const handleConfirmSignal = async () => {
    if (!selectedSignal) return;
    const signalId = selectedSignal.id || selectedSignal._id;
    const result = await useAppStore.getState().voteSignal(signalId, 'confirm');
    if (result.ok) {
      vibrate('success');
      // Refresh signals
      if (radarActive) {
        fetchNearbySignals();
      } else {
        fetchSignals();
      }
    } else {
      vibrate('error');
    }
    setSelectedSignal(null);
  };
  
  const handleDismissSignal = async () => {
    if (!selectedSignal) return;
    const signalId = selectedSignal.id || selectedSignal._id;
    const result = await useAppStore.getState().voteSignal(signalId, 'reject');
    if (result.ok) {
      vibrate('light');
      // Refresh signals
      if (radarActive) {
        fetchNearbySignals();
      } else {
        fetchSignals();
      }
    }
    setSelectedSignal(null);
  };
  
  const radarCenter = userLocation ? [userLocation.lat, userLocation.lng] : mapCenter;
  const radiusOptions = [500, 1000, 2000, 5000];
  
  // Use clustering for zoom < 12
  const useClustering = mapZoom < 12;
  
  return (
    <div className="radar-page-fullscreen" data-testid="radar-page">
      {/* FULLSCREEN MAP */}
      <div className="radar-map-container">
        <MapContainer
          center={mapCenter}
          zoom={14}
          className="radar-map"
          zoomControl={false}
          attributionControl={false}
        >
          {/* Layer 1: Base Map */}
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
          
          <MapController center={mapCenter} zoom={14} />
          <ZoomTracker />
          
          {/* Layer 2: Heatmap - DISABLED for cleaner map */}
          {/* 
          {displayHeatmap && heatmapPoints.length > 0 && (
            <HeatmapLayer ... />
          )}
          */}
          
          {/* Layer 2.5: Risk Zones - DISABLED for cleaner map */}
          {/*
          {riskAnalysis.zones.map((zone, i) => (
            zone.riskLevel !== 'safe' && (
              <Circle
                key={`risk-${i}`}
                center={[zone.center.lat, zone.center.lng]}
                radius={zone.radius}
                pathOptions={{
                  color: getRiskColor(zone.riskLevel),
                  fillColor: getRiskColor(zone.riskLevel),
                  fillOpacity: getRiskOpacity(zone.riskScore),
                  weight: 1,
                  dashArray: zone.riskLevel === 'danger' ? '' : '4, 4',
                }}
              />
            )
          ))}
          */}
          
          {/* Layer 3: Radar Circle */}
          {radarActive && (
            <Circle
              center={radarCenter}
              radius={radarRadius}
              pathOptions={{
                color: '#3B82F6',
                fillColor: '#3B82F6',
                fillOpacity: 0.02,
                weight: 1,
                dashArray: '6, 6',
              }}
            />
          )}
          
          {/* Radar Sweep Animation */}
          <RadarSweepLayer center={radarCenter} radius={radarRadius} active={radarActive} />
          
          {/* Layer 4: User Location */}
          {userLocation && (
            <Marker
              position={[userLocation.lat, userLocation.lng]}
              icon={userLocationIcon}
            />
          )}
          
          {/* Layer 5: Signal Markers - Clean PNG ICONS with zoom scaling */}
          {useClustering ? (
            <MarkerClusterGroup
              chunkedLoading
              iconCreateFunction={createClusterIcon}
              maxClusterRadius={60}
              spiderfyOnMaxZoom={true}
              showCoverageOnHover={false}
            >
              {activeSignals.map((signal) => (
                <Marker
                  key={signal.id || signal._id}
                  position={[signal.lat, signal.lng]}
                  icon={createIconMarker(signal, mapZoom)}
                  eventHandlers={{
                    click: () => handleSignalClick(signal),
                  }}
                />
              ))}
            </MarkerClusterGroup>
          ) : (
            activeSignals.map((signal) => (
              <Marker
                key={signal.id || signal._id}
                position={[signal.lat, signal.lng]}
                icon={createIconMarker(signal, mapZoom)}
                eventHandlers={{
                  click: () => handleSignalClick(signal),
                }}
              />
            ))
          )}
        </MapContainer>
      </div>
      
      {/* FLOATING UI OVERLAYS */}
      
      {/* Top Header */}
      <div className="radar-header">
        <div className="radar-status">
          <div className={`radar-status-dot ${radarActive ? 'active' : ''}`}>
            {radarActive && <div className="radar-status-pulse" />}
          </div>
          <div className="radar-status-text">
            <div className="radar-status-title">
              {radarActive ? 'Радар сканує' : 'Радар вимкнено'}
              {riskAnalysis.overallRisk !== 'low' && radarActive && (
                <span className={`risk-badge risk-${riskAnalysis.overallRisk}`}>
                  {riskAnalysis.overallRisk === 'critical' ? 'НЕБЕЗПЕКА' :
                   riskAnalysis.overallRisk === 'high' ? 'РИЗИК' : 'УВАГА'}
                </span>
              )}
            </div>
            <div className="radar-status-subtitle">
              Київ • {activeSignals.length} сигналів
              {freshCount > 0 && <span className="fresh-badge"> • {freshCount} нових</span>}
            </div>
          </div>
        </div>
        
        <div className="radar-actions">
          <button
            onClick={() => setShowHeatmap(!showHeatmap)}
            className={`radar-action-btn ${showHeatmap ? 'active' : ''}`}
            data-testid="heatmap-btn"
          >
            <Flame size={18} />
          </button>
          <button
            onClick={getLocation}
            disabled={locating}
            className="radar-action-btn"
            data-testid="locate-btn"
          >
            <Navigation size={18} className={locating ? 'animate-pulse' : ''} />
          </button>
          <button
            onClick={() => fetchSignals()}
            disabled={signalsLoading}
            className="radar-action-btn"
            data-testid="refresh-btn"
          >
            <RefreshCw size={18} className={signalsLoading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>
      
      {/* Risk Alert Banner */}
      {riskAlert && (
        <div className="risk-alert-banner">
          <AlertTriangle size={18} />
          <span>{riskAlert.message}</span>
        </div>
      )}
      
      {/* Nearby Signals Panel - ICON ONLY (no text labels) */}
      {radarActive && nearbySignals.length > 0 && (
        <div className="nearby-signals-panel" data-testid="nearby-signals">
          <div className="nearby-signals-header">
            <span className="nearby-signals-title">Поруч</span>
            <span className="nearby-signals-count">{nearbySignals.length}</span>
          </div>
          <div className="nearby-signals-list">
            {nearbySignals.slice(0, 4).map((signal) => {
              const signalType = SIGNAL_TYPES.find(t => t.id === signal.type) || SIGNAL_TYPES[0];
              const dist = userLocation ? calculateDistance(userLocation.lat, userLocation.lng, signal.lat, signal.lng) : null;
              const distStr = dist ? (dist < 1000 ? `${Math.round(dist)}м` : `${(dist/1000).toFixed(1)}км`) : '';
              return (
                <button 
                  key={signal.id || signal._id}
                  className="nearby-signal-item"
                  onClick={() => handleSignalClick(signal)}
                >
                  <img 
                    src={signalType.iconPath || `/icons/${signal.type}.png`} 
                    alt=""
                    className="nearby-signal-icon"
                  />
                  <span className="nearby-signal-dist">{distStr}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
      
      {/* Signal Card Popup */}
      {selectedSignal && (
        <div className="signal-card-overlay" onClick={() => setSelectedSignal(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <SignalCard
              signal={selectedSignal}
              userLocation={userLocation}
              onConfirm={handleConfirmSignal}
              onDismiss={handleDismissSignal}
              onClose={() => setSelectedSignal(null)}
            />
          </div>
        </div>
      )}
      
      {/* Bottom Controls */}
      <div className="radar-bottom-panel">
        {/* Radar Toggle */}
        <button
          onClick={toggleRadar}
          className={`radar-toggle-btn ${radarActive ? 'active' : ''}`}
          data-testid="radar-toggle"
        >
          <Radio size={20} className={radarActive ? 'animate-pulse' : ''} />
          <span>{radarActive ? 'РАДАР АКТИВНИЙ' : 'Увімкнути радар'}</span>
        </button>
        
        {/* Radius Options */}
        {radarActive && (
          <div className="radius-options">
            {radiusOptions.map((r) => (
              <button
                key={r}
                onClick={() => {
                  vibrate('light');
                  setRadarRadius(r);
                }}
                className={`radius-btn ${radarRadius === r ? 'active' : ''}`}
              >
                {r >= 1000 ? `${r/1000}км` : `${r}м`}
              </button>
            ))}
          </div>
        )}
      </div>
      
      {/* Floating Action Button - Report Signal */}
      <button 
        className="fab-report"
        onClick={() => setActiveTab('report')}
        data-testid="fab-report"
      >
        <Plus size={24} />
      </button>
      
      {/* Toast */}
      {toastSignal && (
        <SignalToast 
          signal={toastSignal}
          onClose={() => setToastSignal(null)}
          onView={() => setActiveTab('alerts')}
        />
      )}
    </div>
  );
}
