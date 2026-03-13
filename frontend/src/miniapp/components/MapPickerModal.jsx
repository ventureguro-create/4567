/**
 * Map Picker Component - Select location on map
 */
import { useState, useEffect } from 'react';
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet';
import { MapPin, Check, X } from 'lucide-react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// Custom marker for selected location
const selectedLocationIcon = L.divIcon({
  className: 'selected-location-marker',
  html: `
    <div style="
      width: 40px;
      height: 40px;
      background: #3B82F6;
      border: 4px solid white;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      box-shadow: 0 4px 16px rgba(59, 130, 246, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
    ">
      <div style="
        width: 12px;
        height: 12px;
        background: white;
        border-radius: 50%;
        transform: rotate(45deg);
      "></div>
    </div>
  `,
  iconSize: [40, 40],
  iconAnchor: [20, 40],
});

function LocationMarker({ position, setPosition }) {
  useMapEvents({
    click(e) {
      setPosition(e.latlng);
    },
  });

  return position ? (
    <Marker position={position} icon={selectedLocationIcon} />
  ) : null;
}

export default function MapPickerModal({ isOpen, onClose, onSelect, initialCenter }) {
  const [selectedPosition, setSelectedPosition] = useState(null);
  const [mapCenter] = useState(initialCenter || [50.4501, 30.5234]);

  useEffect(() => {
    if (isOpen) {
      setSelectedPosition(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (selectedPosition) {
      onSelect({
        lat: selectedPosition.lat,
        lng: selectedPosition.lng,
      });
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-[2000] bg-background" data-testid="map-picker-modal">
      {/* Header */}
      <div className="absolute top-0 left-0 right-0 z-[2001] bg-surface/90 backdrop-blur-lg p-4 flex items-center justify-between border-b border-neutral-100">
        <button
          onClick={onClose}
          className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-neutral-100 active:scale-95 transition-all"
        >
          <X size={24} className="text-neutral-700" />
        </button>
        <h2 className="text-lg font-semibold text-neutral-900">
          {selectedPosition ? 'Обрана локація' : 'Натисніть на карту'}
        </h2>
        <div className="w-10" />
      </div>

      {/* Map */}
      <div className="absolute inset-0 pt-16 pb-24">
        <MapContainer
          center={mapCenter}
          zoom={14}
          className="h-full w-full"
          zoomControl={false}
          attributionControl={false}
        >
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          />
          <LocationMarker 
            position={selectedPosition} 
            setPosition={setSelectedPosition} 
          />
        </MapContainer>
      </div>

      {/* Crosshair hint */}
      {!selectedPosition && (
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 pointer-events-none z-[2001]">
          <div className="w-16 h-16 border-2 border-primary/30 rounded-full flex items-center justify-center">
            <div className="w-2 h-2 bg-primary rounded-full"></div>
          </div>
        </div>
      )}

      {/* Bottom panel */}
      <div className="absolute bottom-0 left-0 right-0 z-[2001] bg-surface/90 backdrop-blur-lg p-4 border-t border-neutral-100">
        {selectedPosition ? (
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-neutral-50 rounded-xl">
              <MapPin size={20} className="text-primary" />
              <span className="text-sm font-mono text-neutral-600">
                {selectedPosition.lat.toFixed(5)}, {selectedPosition.lng.toFixed(5)}
              </span>
            </div>
            <button
              onClick={handleConfirm}
              className="w-full py-4 bg-primary text-white rounded-2xl font-semibold flex items-center justify-center gap-3 shadow-lg shadow-primary/20 active:scale-[0.98] transition-transform"
              data-testid="confirm-location-btn"
            >
              <Check size={20} />
              Підтвердити
            </button>
          </div>
        ) : (
          <p className="text-center text-neutral-500 py-2">
            Натисніть на карту, щоб обрати місце
          </p>
        )}
      </div>
    </div>
  );
}
