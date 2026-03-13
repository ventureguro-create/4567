/**
 * Quick Report Modal - Fast signal reporting (Waze-style)
 */
import { useState, useEffect } from 'react';
import { 
  X, 
  MapPin, 
  Camera, 
  Send, 
  Loader2,
  AlertTriangle,
  Trash2,
  Cloud,
  CloudRain,
  Construction,
  Check
} from 'lucide-react';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

// Report types - emoji only
const REPORT_TYPES = [
  { type: 'virus', emoji: '🦠' },
  { type: 'trash', emoji: '🗑' },
  { type: 'rain', emoji: '🌧' },
  { type: 'block', emoji: '🚧' },
  { type: 'police', emoji: '🚔' }
];

// Confidence level badges
const CONFIDENCE_BADGES = {
  low: { label: 'Низький', color: 'bg-gray-100 text-gray-600', dot: 'bg-gray-400' },
  medium: { label: 'Середній', color: 'bg-yellow-100 text-yellow-700', dot: 'bg-yellow-400' },
  high: { label: 'Високий', color: 'bg-green-100 text-green-700', dot: 'bg-green-500' }
};

export default function QuickReportModal({ isOpen, onClose, userLocation, onSuccess }) {
  const [step, setStep] = useState('type'); // type | location | photo | confirm | success
  const [selectedType, setSelectedType] = useState(null);
  const [location, setLocation] = useState(userLocation);
  const [photo, setPhoto] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [gettingLocation, setGettingLocation] = useState(false);

  // Reset when opening
  useEffect(() => {
    if (isOpen) {
      setStep('type');
      setSelectedType(null);
      setLocation(userLocation);
      setPhoto(null);
      setError(null);
      setResult(null);
    }
  }, [isOpen, userLocation]);

  // Get current location
  const getCurrentLocation = () => {
    setGettingLocation(true);
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          setLocation({
            lat: pos.coords.latitude,
            lng: pos.coords.longitude
          });
          setGettingLocation(false);
          setStep('photo');
        },
        (err) => {
          setError('Не вдалося отримати локацію');
          setGettingLocation(false);
        }
      );
    } else {
      setError('Геолокація не підтримується');
      setGettingLocation(false);
    }
  };

  // Handle type selection
  const handleTypeSelect = (type) => {
    setSelectedType(type);
    if (location) {
      setStep('photo');
    } else {
      setStep('location');
    }
  };

  // Handle photo capture
  const handlePhotoChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setPhoto(file);
    }
  };

  // Submit report
  const submitReport = async (withPhoto = false) => {
    if (!selectedType || !location) {
      setError('Виберіть тип та локацію');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      // Create actor ID (for demo, use a random one or from localStorage)
      const actorId = localStorage.getItem('geoRadarActorId') || `web_${Date.now()}`;
      localStorage.setItem('geoRadarActorId', actorId);

      const payload = {
        actorId,
        eventType: selectedType.type,
        lat: location.lat,
        lng: location.lng
      };

      // TODO: Handle photo upload separately if needed

      const response = await fetch(`${API_BASE}/api/geo/report`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await response.json();

      if (data.ok) {
        setResult(data);
        setStep('success');
        if (onSuccess) onSuccess(data);
      } else {
        setError(data.error || 'Помилка при створенні сигналу');
      }
    } catch (err) {
      setError('Помилка мережі');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal content */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden z-10">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-2xl">
            📡
          </h2>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
            data-testid="close-report-modal"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Step 1: Select Type */}
          {step === 'type' && (
            <div className="space-y-4">
              <div className="flex justify-center gap-3 flex-wrap">
                {REPORT_TYPES.map((type) => (
                  <button
                    key={type.type}
                    onClick={() => handleTypeSelect(type)}
                    className="text-4xl p-3 rounded-xl border-2 border-gray-200 hover:border-teal-400 hover:bg-teal-50 transition-all"
                    data-testid={`report-type-${type.type}`}
                  >
                    {type.emoji}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Location */}
          {step === 'location' && (
            <div className="space-y-4 text-center">
              <div className="text-5xl mb-4">{selectedType?.emoji}</div>
              
              <button
                onClick={getCurrentLocation}
                disabled={gettingLocation}
                className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-teal-600 hover:bg-teal-700 text-white rounded-xl font-medium disabled:opacity-50"
                data-testid="get-location-btn"
              >
                {gettingLocation ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <MapPin className="w-5 h-5" />
                )}
                {gettingLocation ? 'Визначаємо...' : 'Поточна локація'}
              </button>
            </div>
          )}

          {/* Step 3: Photo Option */}
          {step === 'photo' && (
            <div className="space-y-4 text-center">
              <div className="text-5xl mb-4">{selectedType?.emoji}</div>
              
              <div className="flex justify-center gap-4 mt-4">
                <label className="text-4xl p-4 rounded-xl border-2 border-gray-200 hover:border-teal-400 hover:bg-teal-50 transition-all cursor-pointer">
                  📷
                  <input
                    type="file"
                    accept="image/*"
                    capture="environment"
                    onChange={(e) => {
                      handlePhotoChange(e);
                      submitReport(true);
                    }}
                    className="hidden"
                    data-testid="photo-input"
                  />
                </label>
                
                <button
                  onClick={() => submitReport(false)}
                  disabled={loading}
                  className="text-4xl p-4 rounded-xl border-2 border-gray-200 hover:border-teal-400 hover:bg-teal-50 transition-all"
                  data-testid="skip-photo-btn"
                >
                  {loading ? '⏳' : '➡️'}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Success */}
          {step === 'success' && result && (
            <div className="space-y-4 text-center">
              <div className="text-5xl">✅ {selectedType?.emoji}</div>
              
              <div className="text-3xl">
                {result.truthScore >= 0.7 ? '🟢' : result.truthScore >= 0.5 ? '🟡' : '⚪'}
              </div>
              
              <button
                onClick={onClose}
                className="text-4xl p-4"
                data-testid="done-btn"
              >
                👍
              </button>
            </div>
          )}
        </div>

        {/* Progress indicator */}
        {step !== 'success' && (
          <div className="px-6 pb-4">
            <div className="flex items-center justify-center gap-2">
              <div className={`w-2 h-2 rounded-full ${step === 'type' ? 'bg-teal-600' : 'bg-gray-300'}`} />
              <div className={`w-2 h-2 rounded-full ${step === 'location' ? 'bg-teal-600' : 'bg-gray-300'}`} />
              <div className={`w-2 h-2 rounded-full ${step === 'photo' ? 'bg-teal-600' : 'bg-gray-300'}`} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
