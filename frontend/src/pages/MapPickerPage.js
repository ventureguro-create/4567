import React, { useState, useEffect, useCallback, useRef } from 'react';
import { MapContainer, TileLayer, Marker, useMapEvents, CircleMarker, Popup } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Fix Leaflet marker icon
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
  iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
  shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
});

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || '';

// Event type icons and colors
const EVENT_CONFIG = {
  virus: { emoji: '🦠', color: '#ef4444', label: 'Вірус' },
  trash: { emoji: '🗑', color: '#f59e0b', label: 'Сміття' },
  rain: { emoji: '🌧', color: '#3b82f6', label: 'Дощ/Потоп' },
  police: { emoji: '🚔', color: '#8b5cf6', label: 'Поліція' },
  accident: { emoji: '🚗', color: '#dc2626', label: 'Аварія' },
  other: { emoji: '📍', color: '#6b7280', label: 'Інше' }
};

// Location picker component
function LocationPicker({ position, setPosition }) {
  useMapEvents({
    click(e) {
      setPosition(e.latlng);
    },
  });

  return position ? <Marker position={position} /> : null;
}

// Event markers component
function EventMarkers({ events }) {
  return events.map((event, idx) => {
    const config = EVENT_CONFIG[event.eventType] || EVENT_CONFIG.other;
    const confidence = event.confidence || 0.5;
    const radius = 8 + (confidence * 10); // Size based on confidence
    
    return (
      <CircleMarker
        key={event.id || idx}
        center={[event.lat, event.lng]}
        radius={radius}
        pathOptions={{
          color: config.color,
          fillColor: config.color,
          fillOpacity: 0.6,
          weight: 2
        }}
      >
        <Popup>
          <div className="text-center">
            <div className="text-2xl mb-1">{config.emoji}</div>
            <div className="font-medium">{config.label}</div>
            {event.confirmations > 0 && (
              <div className="text-xs text-gray-500 mt-1">
                ✓ {event.confirmations} підтверджень
              </div>
            )}
          </div>
        </Popup>
      </CircleMarker>
    );
  });
}

export default function MapPickerPage() {
  const [position, setPosition] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [token, setToken] = useState(null);
  const mapRef = useRef(null);

  // Default center (Kyiv)
  const defaultCenter = [50.4501, 30.5234];

  // Get token from URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenParam = params.get('token');
    if (tokenParam) {
      setToken(tokenParam);
    } else {
      setError('Токен не знайдено. Відкрийте карту через бот.');
    }
  }, []);

  // Load existing events from backend
  useEffect(() => {
    async function loadEvents() {
      try {
        const response = await fetch(`${BACKEND_URL}/api/geo/map?days=7&limit=200`);
        const data = await response.json();
        if (data.events) {
          setEvents(data.events);
        }
      } catch (err) {
        console.error('Failed to load events:', err);
      }
    }
    loadEvents();
  }, []);

  // Try to get user's location on load
  useEffect(() => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const userPos = { lat: pos.coords.latitude, lng: pos.coords.longitude };
          setPosition(userPos);
          if (mapRef.current) {
            mapRef.current.flyTo(userPos, 15);
          }
        },
        () => {
          // Geolocation denied, use default
        }
      );
    }
  }, []);

  const handleConfirm = useCallback(async () => {
    if (!position || !token) return;

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${BACKEND_URL}/api/geo/location-picker/set`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          token,
          lat: position.lat,
          lng: position.lng,
        }),
      });

      const data = await response.json();

      if (data.ok) {
        setSuccess(true);
        // Close WebApp after 1.5 seconds
        setTimeout(() => {
          if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.close();
          }
        }, 1500);
      } else {
        setError(data.error || 'Помилка збереження локації');
      }
    } catch (err) {
      setError('Помилка з\'єднання');
    } finally {
      setLoading(false);
    }
  }, [position, token]);

  if (success) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center p-8">
          <div className="text-6xl mb-4">✅</div>
          <h2 className="text-xl text-slate-800 font-semibold">Локацію збережено!</h2>
          <p className="text-slate-500 mt-2">Поверніться до бота</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen bg-slate-50 flex flex-col">
      {/* Header - Light theme */}
      <div className="p-4 bg-white border-b border-slate-200 flex-shrink-0 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-800 text-center">
          🗺 Виберіть точку на карті
        </h1>
        <p className="text-sm text-slate-500 text-center mt-1">
          Натисніть на карту, щоб вказати місце
        </p>
      </div>

      {/* Map Container */}
      <div className="flex-1 relative" style={{ minHeight: '400px' }}>
        <MapContainer
          center={defaultCenter}
          zoom={12}
          style={{ height: '100%', width: '100%', position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }}
          ref={mapRef}
        >
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          />
          {/* Existing events from backend */}
          <EventMarkers events={events} />
          {/* User's selection marker */}
          <LocationPicker position={position} setPosition={setPosition} />
        </MapContainer>

        {/* Crosshair hint */}
        {!position && (
          <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 pointer-events-none z-[1000]">
            <div className="bg-white/90 shadow-lg px-4 py-2 rounded-lg text-slate-700 text-sm border border-slate-200">
              Натисніть на карту
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="absolute bottom-4 left-4 z-[1000] bg-white/95 rounded-lg shadow-md p-2 text-xs">
          <div className="font-medium text-slate-600 mb-1">Сигнали:</div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(EVENT_CONFIG).slice(0, 4).map(([key, cfg]) => (
              <span key={key} className="flex items-center gap-1">
                <span style={{ color: cfg.color }}>{cfg.emoji}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Bottom Panel - Light theme */}
      <div className="p-4 bg-white border-t border-slate-200 shadow-lg">
        {error && (
          <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
            {error}
          </div>
        )}

        {position && (
          <div className="mb-3 p-3 bg-slate-100 rounded-lg">
            <p className="text-sm text-slate-600">
              📍 {position.lat.toFixed(6)}, {position.lng.toFixed(6)}
            </p>
          </div>
        )}

        <button
          onClick={handleConfirm}
          disabled={!position || loading}
          data-testid="confirm-location-btn"
          className={`w-full py-3 px-4 rounded-xl font-medium transition-all ${
            position && !loading
              ? 'bg-blue-600 hover:bg-blue-700 text-white active:scale-[0.98] shadow-md'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed'
          }`}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Зберігаю...
            </span>
          ) : (
            '✓ Підтвердити локацію'
          )}
        </button>
      </div>
    </div>
  );
}
