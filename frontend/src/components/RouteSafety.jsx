/**
 * RouteSafety Component
 * Route safety checker with hazard visualization
 */
import { useState, useCallback } from 'react';
import { Route, Shield, AlertTriangle, Navigation, Compass } from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

export default function RouteSafety({ userLocation, onHazardsChange }) {
  const [startPoint, setStartPoint] = useState(null);
  const [endPoint, setEndPoint] = useState(null);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState(null);
  const [safeDirection, setSafeDirection] = useState(null);
  
  // Use user location as start
  const useCurrentLocation = () => {
    if (userLocation) {
      setStartPoint({ lat: userLocation.lat, lng: userLocation.lng });
    }
  };
  
  // Check route safety
  const checkRoute = useCallback(async () => {
    if (!startPoint || !endPoint) return;
    
    setChecking(true);
    try {
      // Generate simple route points (straight line for now)
      const points = [];
      const steps = 10;
      for (let i = 0; i <= steps; i++) {
        points.push({
          lat: startPoint.lat + (endPoint.lat - startPoint.lat) * (i / steps),
          lng: startPoint.lng + (endPoint.lng - startPoint.lng) * (i / steps)
        });
      }
      
      const res = await fetch(`${API_BASE}/api/geo/route/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ points, days: 3 })
      });
      
      const data = await res.json();
      setResult(data);
      
      if (onHazardsChange && data.hazards) {
        onHazardsChange(data.hazards);
      }
    } catch (err) {
      console.error('Route check error:', err);
    } finally {
      setChecking(false);
    }
  }, [startPoint, endPoint, onHazardsChange]);
  
  // Get safe direction
  const fetchSafeDirection = useCallback(async () => {
    if (!userLocation) return;
    
    try {
      const res = await fetch(
        `${API_BASE}/api/geo/route/direction?lat=${userLocation.lat}&lng=${userLocation.lng}&radius=1000`
      );
      const data = await res.json();
      if (data.ok) {
        setSafeDirection(data);
      }
    } catch (err) {
      console.error('Safe direction error:', err);
    }
  }, [userLocation]);
  
  // Fetch safe direction on user location change
  useState(() => {
    if (userLocation) {
      fetchSafeDirection();
    }
  }, [userLocation, fetchSafeDirection]);
  
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4" data-testid="route-safety">
      {/* Header */}
      <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
        <Route className="w-4 h-4 text-teal-500" />
        Безпека маршруту
      </h3>
      
      {/* Safe direction indicator */}
      {safeDirection && (
        <div className="bg-gradient-to-r from-green-50 to-teal-50 rounded-lg p-3 mb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Compass className="w-5 h-5 text-green-600" />
              <span className="text-sm text-gray-700">Безпечний напрямок:</span>
            </div>
            <span className="text-lg font-bold text-green-600">
              {safeDirection.safestDirection}
            </span>
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Уникайте напрямку: <span className="text-red-500 font-medium">{safeDirection.dangerousDirection}</span>
          </div>
        </div>
      )}
      
      {/* Route input */}
      <div className="space-y-3 mb-4">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Початок</label>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="lat, lng"
              value={startPoint ? `${startPoint.lat.toFixed(4)}, ${startPoint.lng.toFixed(4)}` : ''}
              onChange={(e) => {
                const [lat, lng] = e.target.value.split(',').map(v => parseFloat(v.trim()));
                if (!isNaN(lat) && !isNaN(lng)) {
                  setStartPoint({ lat, lng });
                }
              }}
              className="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2"
            />
            <button
              onClick={useCurrentLocation}
              disabled={!userLocation}
              className="px-3 py-2 bg-teal-500 text-white rounded-lg text-sm disabled:opacity-50"
              title="Моя позиція"
            >
              <Navigation className="w-4 h-4" />
            </button>
          </div>
        </div>
        
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Кінець</label>
          <input
            type="text"
            placeholder="lat, lng (напр. 50.4520, 30.5100)"
            value={endPoint ? `${endPoint.lat.toFixed(4)}, ${endPoint.lng.toFixed(4)}` : ''}
            onChange={(e) => {
              const [lat, lng] = e.target.value.split(',').map(v => parseFloat(v.trim()));
              if (!isNaN(lat) && !isNaN(lng)) {
                setEndPoint({ lat, lng });
              }
            }}
            className="w-full text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2"
          />
        </div>
        
        <button
          onClick={checkRoute}
          disabled={!startPoint || !endPoint || checking}
          className="w-full py-2 bg-teal-500 hover:bg-teal-600 text-white rounded-lg text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-2"
          data-testid="check-route-btn"
        >
          {checking ? (
            <>Перевірка...</>
          ) : (
            <>
              <Shield className="w-4 h-4" />
              Перевірити маршрут
            </>
          )}
        </button>
      </div>
      
      {/* Results */}
      {result && (
        <div className={`rounded-lg p-3 ${
          result.isSafe 
            ? 'bg-green-50 border border-green-200' 
            : 'bg-red-50 border border-red-200'
        }`}>
          <div className="flex items-center gap-2 mb-2">
            {result.isSafe ? (
              <Shield className="w-5 h-5 text-green-600" />
            ) : (
              <AlertTriangle className="w-5 h-5 text-red-600" />
            )}
            <span className={`font-medium ${result.isSafe ? 'text-green-700' : 'text-red-700'}`}>
              {result.message}
            </span>
          </div>
          
          {result.hazardCount > 0 && (
            <div className="mt-2 space-y-1">
              <div className="text-xs text-gray-600">
                Знайдено небезпек: {result.hazardCount}
              </div>
              <div className="text-xs text-gray-600">
                Рівень ризику: {(result.riskScore * 100).toFixed(0)}%
              </div>
              
              {/* Hazard list */}
              <div className="mt-2 max-h-32 overflow-y-auto space-y-1">
                {result.hazards?.slice(0, 5).map((h, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs bg-white/50 rounded px-2 py-1">
                    <span>{h.eventType === 'virus' ? '🦠' : h.eventType === 'trash' ? '🗑️' : '⚠️'}</span>
                    <span className="text-gray-700">{h.title || h.eventType}</span>
                    <span className="text-gray-400">{h.distance}м</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
