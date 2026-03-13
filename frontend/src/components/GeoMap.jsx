/**
 * GeoMap Component - Production Leaflet Map with Radar Mode
 * Real map with markers, clusters, user location pulse, radar circle
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, ZoomControl, Circle, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Maximize2, Minimize2, MapPin, Eye, ExternalLink, Navigation, Radio, AlertTriangle } from 'lucide-react';

// Fix default marker icon issue with webpack
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/images/marker-shadow.png',
});

// CSS for pulse animation (injected once)
const pulseStyles = `
  .radar-user-marker {
    position: relative;
    width: 16px;
    height: 16px;
    background: #14b8a6;
    border-radius: 50%;
    border: 3px solid white;
    box-shadow: 0 2px 8px rgba(20, 184, 166, 0.5);
  }
  .radar-user-marker::after {
    content: "";
    position: absolute;
    top: -10px;
    left: -10px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: rgba(20, 184, 166, 0.3);
    animation: radarPulse 2s infinite;
  }
  @keyframes radarPulse {
    0% { transform: scale(0.5); opacity: 1; }
    100% { transform: scale(1.5); opacity: 0; }
  }
  .radar-event-highlight {
    animation: eventPulse 1.5s ease-in-out infinite;
  }
  @keyframes eventPulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.15); }
  }
`;

// Inject styles once
if (typeof document !== 'undefined' && !document.getElementById('radar-pulse-styles')) {
  const style = document.createElement('style');
  style.id = 'radar-pulse-styles';
  style.textContent = pulseStyles;
  document.head.appendChild(style);
}

// User pulse marker icon
const createUserIcon = () => {
  return L.divIcon({
    className: '',
    html: `<div class="radar-user-marker"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  });
};

// Custom icons - emoji only
const EVENT_ICONS = {
  virus: "🦠",
  trash: "🗑",
  rain: "🌧",
  block: "🚧",
  police: "🚔"
};

const getEventIcon = (eventType, isInsideRadius = false) => {
  const icon = EVENT_ICONS[eventType] || "🚔";
  const size = isInsideRadius ? 18 : 14;
  const highlight = isInsideRadius ? 'class="radar-event-highlight"' : '';
  
  return L.divIcon({
    className: '',
    html: `<span ${highlight} style="font-size:${size}px;line-height:1;display:block;">${icon}</span>`,
    iconSize: [size, size],
    iconAnchor: [size/2, size/2],
    popupAnchor: [0, -7],
  });
};

// Component to fit bounds to markers
function FitBounds({ points }) {
  const map = useMap();
  
  useEffect(() => {
    if (points.length > 0) {
      const validPoints = points.filter(p => p.lat && p.lng);
      if (validPoints.length > 0) {
        const bounds = L.latLngBounds(validPoints.map(p => [p.lat, p.lng]));
        map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
      }
    }
  }, [points, map]);
  
  return null;
}

// Component to fly to selected marker
function FlyToMarker({ points, selectedMarkerId }) {
  const map = useMap();
  
  useEffect(() => {
    if (selectedMarkerId && points.length > 0) {
      const point = points.find(p => p.id === selectedMarkerId);
      if (point && point.lat && point.lng) {
        map.flyTo([point.lat, point.lng], 16, { duration: 1 });
      }
    }
  }, [selectedMarkerId, points, map]);
  
  return null;
}

// Component to center on user location
function CenterOnUser({ userLocation, shouldCenter }) {
  const map = useMap();
  
  useEffect(() => {
    if (shouldCenter && userLocation) {
      map.flyTo([userLocation.lat, userLocation.lng], 15, { duration: 1.5 });
    }
  }, [shouldCenter, userLocation, map]);
  
  return null;
}

// Custom cluster icon
const createClusterCustomIcon = (cluster) => {
  const count = cluster.getChildCount();
  let dimension = 26;
  let fontSize = '11px';
  
  if (count >= 100) {
    dimension = 36;
    fontSize = '13px';
  } else if (count >= 10) {
    dimension = 30;
    fontSize = '12px';
  }
  
  return L.divIcon({
    html: `<div style="
      background: linear-gradient(135deg, #14b8a6, #06b6d4);
      color: white;
      width: ${dimension}px;
      height: ${dimension}px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: bold;
      font-size: ${fontSize};
      box-shadow: 0 2px 6px rgba(0,0,0,0.2);
      border: 2px solid white;
    ">${count}</div>`,
    className: '',
    iconSize: L.point(dimension, dimension, true),
  });
};

export default function GeoMap({ 
  points = [], 
  onPointClick, 
  selectedMarkerId, 
  onMapReady,
  radarMode = false,
  radarRadius = 1000,
  onUserLocationChange
}) {
  const [fullscreen, setFullscreen] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [locationError, setLocationError] = useState(null);
  const [isLocating, setIsLocating] = useState(false);
  const [shouldCenterUser, setShouldCenterUser] = useState(false);
  const mapRef = useRef(null);
  const watchIdRef = useRef(null);
  
  // Default center (Kyiv)
  const defaultCenter = [50.4501, 30.5234];
  const defaultZoom = 11;
  
  // Calculate center from points
  const getCenter = () => {
    if (userLocation) return [userLocation.lat, userLocation.lng];
    if (points.length === 0) return defaultCenter;
    const validPoints = points.filter(p => p.lat && p.lng);
    if (validPoints.length === 0) return defaultCenter;
    
    const avgLat = validPoints.reduce((sum, p) => sum + p.lat, 0) / validPoints.length;
    const avgLng = validPoints.reduce((sum, p) => sum + p.lng, 0) / validPoints.length;
    return [avgLat, avgLng];
  };

  // Start watching user location
  const startLocationWatch = useCallback(() => {
    if (!navigator.geolocation) {
      setLocationError('Geolocation не підтримується');
      return;
    }
    
    setIsLocating(true);
    setLocationError(null);
    
    // Clear existing watch
    if (watchIdRef.current) {
      navigator.geolocation.clearWatch(watchIdRef.current);
    }
    
    watchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        const newLocation = {
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracy: position.coords.accuracy
        };
        setUserLocation(newLocation);
        setIsLocating(false);
        setLocationError(null);
        
        if (onUserLocationChange) {
          onUserLocationChange(newLocation);
        }
      },
      (error) => {
        setIsLocating(false);
        switch(error.code) {
          case error.PERMISSION_DENIED:
            setLocationError('Доступ до геолокації заборонено');
            break;
          case error.POSITION_UNAVAILABLE:
            setLocationError('Позиція недоступна');
            break;
          case error.TIMEOUT:
            setLocationError('Таймаут запиту');
            break;
          default:
            setLocationError('Помилка геолокації');
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge: 10000,
        timeout: 15000
      }
    );
  }, [onUserLocationChange]);

  // Stop watching location
  const stopLocationWatch = useCallback(() => {
    if (watchIdRef.current) {
      navigator.geolocation.clearWatch(watchIdRef.current);
      watchIdRef.current = null;
    }
  }, []);

  // Center on user
  const centerOnUser = useCallback(() => {
    if (userLocation) {
      setShouldCenterUser(true);
      setTimeout(() => setShouldCenterUser(false), 100);
    } else {
      startLocationWatch();
      setShouldCenterUser(true);
      setTimeout(() => setShouldCenterUser(false), 2000);
    }
  }, [userLocation, startLocationWatch]);

  // Cleanup on unmount
  useEffect(() => {
    return () => stopLocationWatch();
  }, [stopLocationWatch]);

  // Auto-start location in radar mode
  useEffect(() => {
    if (radarMode && !userLocation) {
      startLocationWatch();
    }
  }, [radarMode, userLocation, startLocationWatch]);

  const handleMarkerClick = (point) => {
    setSelectedPoint(point);
    if (onPointClick) onPointClick(point);
  };

  // Count events inside radius
  const insideRadiusCount = points.filter(p => p.isInsideRadius).length;

  return (
    <div className={`relative ${fullscreen ? 'fixed inset-0 z-50 bg-white' : 'h-full'}`}>
      {/* Controls row */}
      <div className="absolute top-3 left-3 right-3 z-[1000] flex items-center justify-between">
        {/* Left: Points counter + Radar alert */}
        <div className="flex items-center gap-2">
          <div className="bg-white shadow-md px-3 py-2 rounded-lg text-sm font-medium text-gray-700">
            <MapPin className="w-4 h-4 inline mr-1 text-teal-500" />
            {points.length} events
          </div>
          
          {radarMode && insideRadiusCount > 0 && (
            <div className="bg-amber-50 border border-amber-200 shadow-md px-3 py-2 rounded-lg text-sm font-medium text-amber-700 flex items-center gap-2 animate-pulse">
              <AlertTriangle className="w-4 h-4" />
              {insideRadiusCount} поруч
            </div>
          )}
        </div>
        
        {/* Right: Location + Fullscreen */}
        <div className="flex items-center gap-2">
          {/* Location button */}
          <button
            onClick={centerOnUser}
            disabled={isLocating}
            className={`bg-white shadow-md px-3 py-2 rounded-lg flex items-center gap-2 text-sm font-medium transition-colors ${
              userLocation 
                ? 'text-teal-600 hover:bg-teal-50' 
                : 'text-gray-700 hover:bg-gray-50'
            } ${isLocating ? 'opacity-50' : ''}`}
            title="Моя позиція"
          >
            <Navigation className={`w-4 h-4 ${isLocating ? 'animate-pulse' : ''} ${userLocation ? 'fill-current' : ''}`} />
            {isLocating ? 'Пошук...' : userLocation ? 'Моя позиція' : 'Знайти мене'}
          </button>
          
          {/* Fullscreen toggle */}
          <button
            onClick={() => setFullscreen(!fullscreen)}
            className="bg-white shadow-md px-3 py-2 rounded-lg flex items-center gap-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            {fullscreen ? (
              <>
                <Minimize2 className="w-4 h-4" />
                Вихід
              </>
            ) : (
              <>
                <Maximize2 className="w-4 h-4" />
                Повний екран
              </>
            )}
          </button>
        </div>
      </div>
      
      {/* Location error */}
      {locationError && (
        <div className="absolute top-16 left-3 z-[1000] bg-red-50 border border-red-200 text-red-700 px-3 py-2 rounded-lg text-sm">
          {locationError}
        </div>
      )}

      <MapContainer
        ref={mapRef}
        center={getCenter()}
        zoom={userLocation ? 14 : defaultZoom}
        zoomControl={false}
        style={{ height: fullscreen ? '100vh' : '100%', width: '100%', minHeight: '500px' }}
        className="rounded-b-xl"
      >
        <ZoomControl position="bottomright" />
        
        {/* OpenStreetMap tiles */}
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        
        {/* Fit bounds to markers (only if no user location) */}
        {points.length > 0 && !userLocation && <FitBounds points={points} />}
        
        {/* Fly to selected marker */}
        {selectedMarkerId && <FlyToMarker points={points} selectedMarkerId={selectedMarkerId} />}
        
        {/* Center on user */}
        <CenterOnUser userLocation={userLocation} shouldCenter={shouldCenterUser} />
        
        {/* Radar circle */}
        {userLocation && radarMode && (
          <Circle
            center={[userLocation.lat, userLocation.lng]}
            radius={radarRadius}
            pathOptions={{
              color: '#14b8a6',
              weight: 2,
              fillColor: '#14b8a6',
              fillOpacity: 0.08
            }}
          />
        )}
        
        {/* User location marker */}
        {userLocation && (
          <Marker
            position={[userLocation.lat, userLocation.lng]}
            icon={createUserIcon()}
            zIndexOffset={2000}
          >
            <Popup>
              <div className="text-sm">
                <strong>Ваша позиція</strong>
                <br />
                <span className="text-gray-500">
                  {userLocation.lat.toFixed(5)}, {userLocation.lng.toFixed(5)}
                </span>
                {userLocation.accuracy && (
                  <><br /><span className="text-gray-400">Точність: ~{Math.round(userLocation.accuracy)}м</span></>
                )}
              </div>
            </Popup>
          </Marker>
        )}
        
        {/* Clustered markers */}
        <MarkerClusterGroup
          chunkedLoading
          iconCreateFunction={createClusterCustomIcon}
          maxClusterRadius={25}
          disableClusteringAtZoom={13}
          spiderfyOnMaxZoom={true}
          showCoverageOnHover={false}
        >
          {points.map((point, index) => {
            if (!point.lat || !point.lng) return null;
            
            const icon = getEventIcon(point.eventType, point.isInsideRadius);
            
            return (
              <Marker
                key={point.id || `point-${index}`}
                position={[point.lat, point.lng]}
                icon={icon}
                zIndexOffset={point.isInsideRadius ? 1000 : 0}
                eventHandlers={{
                  click: () => handleMarkerClick(point)
                }}
              >
                <Popup className="custom-popup" maxWidth={300}>
                  <div className="p-1">
                    <h3 className="font-semibold text-gray-900 text-sm mb-1">
                      {point.title}
                    </h3>
                    
                    {point.addressText && point.addressText !== point.title && (
                      <p className="text-xs text-gray-500 mb-2">{point.addressText}</p>
                    )}
                    
                    {/* Distance if in radar mode */}
                    {point.distanceMeters !== undefined && (
                      <p className={`text-xs mb-2 font-medium ${point.isInsideRadius ? 'text-teal-600' : 'text-gray-500'}`}>
                        📏 {point.distanceMeters < 1000 ? `${point.distanceMeters} м` : `${(point.distanceMeters/1000).toFixed(1)} км`}
                        {point.minutesAgo !== undefined && (
                          <> • 🕐 {point.minutesAgo < 60 ? `${point.minutesAgo} хв` : `${Math.floor(point.minutesAgo/60)} год`} тому</>
                        )}
                      </p>
                    )}
                    
                    <div className="flex items-center gap-3 text-xs text-gray-500 mb-2">
                      <span className={`px-2 py-0.5 rounded ${
                        point.eventType === 'food' ? 'bg-orange-100 text-orange-700' :
                        point.eventType === 'venue' ? 'bg-purple-100 text-purple-700' :
                        point.eventType === 'traffic' ? 'bg-red-100 text-red-700' :
                        'bg-teal-100 text-teal-700'
                      }`}>
                        {point.eventType}
                      </span>
                      
                      {point.metrics?.views > 0 && (
                        <span className="flex items-center gap-1">
                          <Eye className="w-3 h-3" />
                          {point.metrics.views}
                        </span>
                      )}
                      
                      {point.freshnessLabel && (
                        <span className={`px-2 py-0.5 rounded ${
                          point.freshnessLabel === 'hot' ? 'bg-red-100 text-red-700' :
                          point.freshnessLabel === 'recent' ? 'bg-amber-100 text-amber-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {point.freshnessLabel === 'hot' ? '🔥 гаряче' : 
                           point.freshnessLabel === 'recent' ? 'нещодавно' : 'давно'}
                        </span>
                      )}
                    </div>
                    
                    {point.evidenceText && (
                      <p className="text-xs text-gray-600 line-clamp-3 mb-2">
                        {point.evidenceText}
                      </p>
                    )}
                    
                    {point.source?.username && (
                      <a
                        href={`https://t.me/${point.source.username}/${point.source.messageId || ''}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-teal-600 hover:underline flex items-center gap-1"
                      >
                        <ExternalLink className="w-3 h-3" />
                        @{point.source.username}
                      </a>
                    )}
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MarkerClusterGroup>
      </MapContainer>
    </div>
  );
}
