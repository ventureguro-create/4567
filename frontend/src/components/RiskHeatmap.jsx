/**
 * RiskHeatmap Component
 * Displays severity-based risk zones on map
 */
import { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Shield, RefreshCw } from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// Risk level colors
const RISK_COLORS = {
  critical: { bg: 'bg-red-500', text: 'text-red-700', color: '#ef4444' },
  high: { bg: 'bg-orange-500', text: 'text-orange-700', color: '#f97316' },
  medium: { bg: 'bg-amber-500', text: 'text-amber-700', color: '#f59e0b' },
  low: { bg: 'bg-yellow-400', text: 'text-yellow-700', color: '#facc15' },
  minimal: { bg: 'bg-green-400', text: 'text-green-700', color: '#4ade80' }
};

export default function RiskHeatmap({ onRiskZonesChange }) {
  const [zones, setZones] = useState([]);
  const [loading, setLoading] = useState(false);
  const [days, setDays] = useState(7);
  const [showOnMap, setShowOnMap] = useState(true);
  
  // Fetch risk data
  const fetchRisk = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/geo/risk?days=${days}`);
      const data = await res.json();
      if (data.ok) {
        setZones(data.zones || []);
        if (onRiskZonesChange && showOnMap) {
          onRiskZonesChange(data.zones);
        }
      }
    } catch (err) {
      console.error('Risk fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [days, showOnMap, onRiskZonesChange]);
  
  useEffect(() => {
    fetchRisk();
  }, [fetchRisk]);
  
  // Toggle map display
  const toggleMapDisplay = () => {
    const newShow = !showOnMap;
    setShowOnMap(newShow);
    if (onRiskZonesChange) {
      onRiskZonesChange(newShow ? zones : []);
    }
  };
  
  // Stats
  const criticalCount = zones.filter(z => z.riskLevel === 'critical').length;
  const highCount = zones.filter(z => z.riskLevel === 'high').length;
  const mediumCount = zones.filter(z => z.riskLevel === 'medium').length;
  
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4" data-testid="risk-heatmap">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
          <Shield className="w-4 h-4 text-teal-500" />
          Карта ризиків
        </h3>
        
        <div className="flex items-center gap-2">
          <select
            value={days}
            onChange={(e) => setDays(parseInt(e.target.value))}
            className="text-xs bg-gray-100 border-0 rounded px-2 py-1"
          >
            <option value={3}>3 дні</option>
            <option value={7}>7 днів</option>
            <option value={14}>14 днів</option>
          </select>
          
          <button
            onClick={fetchRisk}
            disabled={loading}
            className="p-1.5 rounded hover:bg-gray-100"
          >
            <RefreshCw className={`w-4 h-4 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
      
      {/* Risk summary */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <div className="bg-red-50 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-red-600">{criticalCount}</div>
          <div className="text-xs text-red-500">Критичних</div>
        </div>
        <div className="bg-orange-50 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-orange-600">{highCount}</div>
          <div className="text-xs text-orange-500">Високих</div>
        </div>
        <div className="bg-amber-50 rounded-lg p-2 text-center">
          <div className="text-lg font-bold text-amber-600">{mediumCount}</div>
          <div className="text-xs text-amber-500">Середніх</div>
        </div>
      </div>
      
      {/* Toggle */}
      <div className="flex items-center justify-between mb-3 pb-3 border-b border-gray-100">
        <span className="text-sm text-gray-600">Показати на карті</span>
        <button
          onClick={toggleMapDisplay}
          className={`relative w-11 h-6 rounded-full transition-colors ${
            showOnMap ? 'bg-teal-500' : 'bg-gray-300'
          }`}
        >
          <span
            className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-transform ${
              showOnMap ? 'left-6' : 'left-1'
            }`}
          />
        </button>
      </div>
      
      {/* Top risk zones */}
      <div className="space-y-2 max-h-48 overflow-y-auto">
        {zones.slice(0, 10).map((zone, i) => {
          const colors = RISK_COLORS[zone.riskLevel] || RISK_COLORS.minimal;
          return (
            <div
              key={`${zone.lat}-${zone.lng}-${i}`}
              className="flex items-center justify-between p-2 bg-gray-50 rounded-lg"
            >
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${colors.bg}`} />
                <span className="text-sm text-gray-700">{zone.dominantType}</span>
                <span className="text-xs text-gray-400">({zone.count})</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium ${colors.text}`}>
                  {(zone.riskScore * 100).toFixed(0)}%
                </span>
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Legend */}
      <div className="mt-4 pt-3 border-t border-gray-100">
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(RISK_COLORS).map(([level, colors]) => (
            <span key={level} className="flex items-center gap-1">
              <span className={`w-2 h-2 rounded-full ${colors.bg}`} />
              <span className="text-gray-500">{level}</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
