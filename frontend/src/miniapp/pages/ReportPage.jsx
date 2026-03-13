/**
 * Report Page - Modern Signal Creation with Photo
 * Flow: Type → Location + Photo + Description → Submit
 * Privacy-first approach
 */
import { useState, useRef } from 'react';
import { MapPin, Send, Check, ChevronLeft, Loader2, Camera, X, Image, RefreshCw } from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { requestLocation, vibrate, getTelegramUser } from '../lib/telegram';
import { SIGNAL_TYPES } from '../lib/signalTypes';
import MapPickerModal from '../components/MapPickerModal';

const API_BASE = process.env.REACT_APP_BACKEND_URL || '';

export default function ReportPage() {
  const { userLocation, setUserLocation, setActiveTab } = useAppStore();
  
  const [step, setStep] = useState('type');
  const [selectedType, setSelectedType] = useState(null);
  const [location, setLocation] = useState(null);
  const [description, setDescription] = useState('');
  const [photo, setPhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [locating, setLocating] = useState(false);
  const [showMapPicker, setShowMapPicker] = useState(false);
  
  const fileInputRef = useRef(null);
  
  // Handle type selection - go to create screen
  const handleTypeSelect = async (type) => {
    vibrate('light');
    setSelectedType(type);
    
    // Auto-detect location
    setLocating(true);
    try {
      const loc = await requestLocation();
      if (loc && loc.lat && loc.lng) {
        setLocation(loc);
        setUserLocation(loc);
      } else {
        // Fallback to Kyiv
        const fallbackLoc = { lat: 50.4501, lng: 30.5234 };
        setLocation(fallbackLoc);
        setUserLocation(fallbackLoc);
      }
    } catch (err) {
      // Fallback
      const fallbackLoc = { lat: 50.4501, lng: 30.5234 };
      setLocation(fallbackLoc);
      setUserLocation(fallbackLoc);
    } finally {
      setLocating(false);
    }
    
    setStep('create');
  };
  
  // Handle photo capture
  const handlePhotoCapture = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    vibrate('light');
    setPhoto(file);
    
    // Create preview URL
    const url = URL.createObjectURL(file);
    setPhotoPreview(url);
  };
  
  // Open camera
  const openCamera = () => {
    vibrate('light');
    fileInputRef.current?.click();
  };
  
  // Remove photo
  const removePhoto = () => {
    vibrate('light');
    setPhoto(null);
    if (photoPreview) {
      URL.revokeObjectURL(photoPreview);
      setPhotoPreview(null);
    }
  };
  
  // Handle map location select
  const handleMapSelect = (loc) => {
    setLocation(loc);
    setUserLocation(loc);
    vibrate('success');
  };
  
  // Submit signal with photo
  const handleSubmit = async () => {
    if (!selectedType || !location) return;
    
    setLoading(true);
    vibrate('medium');
    
    try {
      const telegramUser = getTelegramUser();
      
      // Create FormData for multipart upload
      const formData = new FormData();
      formData.append('type', selectedType.id);
      formData.append('lat', location.lat.toString());
      formData.append('lng', location.lng.toString());
      formData.append('description', description);
      formData.append('userId', telegramUser?.id || 'anonymous');
      formData.append('username', telegramUser?.username || '');
      
      if (photo) {
        formData.append('photo', photo);
      }
      
      const response = await fetch(`${API_BASE}/api/geo/miniapp/report-with-photo`, {
        method: 'POST',
        body: formData,
      });
      
      const result = await response.json();
      
      if (result.ok) {
        setStep('success');
        vibrate('success');
        setTimeout(() => {
          // Reset state
          setSelectedType(null);
          setLocation(null);
          setDescription('');
          removePhoto();
          setStep('type');
          setActiveTab('radar');
        }, 2500);
      } else {
        vibrate('error');
        alert(result.error || 'Не вдалося надіслати');
      }
    } catch (err) {
      console.error('Submit error:', err);
      vibrate('error');
      alert('Помилка відправки');
    } finally {
      setLoading(false);
    }
  };
  
  const goBack = () => {
    vibrate('light');
    setStep('type');
    setSelectedType(null);
    setLocation(null);
    setDescription('');
    removePhoto();
  };
  
  // Success Screen
  if (step === 'success') {
    return (
      <div className="h-full flex items-center justify-center bg-background p-6" data-testid="report-success">
        <div className="text-center animate-fade-in max-w-xs">
          <div className="w-20 h-20 bg-success rounded-full flex items-center justify-center mx-auto mb-6 animate-[pulse_0.5s_ease-out]">
            <Check size={40} className="text-white" />
          </div>
          <h2 className="text-xl font-bold text-neutral-900 mb-2">Сигнал надіслано</h2>
          <p className="text-neutral-500 text-sm leading-relaxed mb-4">
            Дякуємо за ваш сигнал!<br/>
            Він допомагає іншим користувачам<br/>
            бачити ситуацію в місті.
          </p>
          <div className="flex items-center justify-center gap-4 text-sm">
            <span className="flex items-center gap-1.5 px-3 py-1.5 bg-success/10 rounded-full text-success font-medium">
              +10 XP
            </span>
            <span className="flex items-center gap-1.5 px-3 py-1.5 bg-primary/10 rounded-full text-primary font-medium">
              +1 Довіра
            </span>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className="h-full flex flex-col bg-background pb-[80px]" data-testid="report-page">
      {/* Hidden file input for camera */}
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handlePhotoCapture}
        className="hidden"
        data-testid="camera-input"
      />
      
      {/* Header */}
      <div className="flex items-center justify-between p-4 bg-surface">
        {step === 'create' ? (
          <button 
            onClick={goBack}
            className="w-10 h-10 flex items-center justify-center rounded-xl hover:bg-neutral-100 active:scale-95 transition-all"
            data-testid="back-btn"
          >
            <ChevronLeft size={24} className="text-neutral-700" />
          </button>
        ) : (
          <div className="w-10" />
        )}
        <h1 className="text-lg font-semibold text-neutral-900">
          {step === 'type' ? 'Новий сигнал' : selectedType?.labelUa || 'Сигнал'}
        </h1>
        <div className="w-10" />
      </div>
      
      {/* Step 1: Select Type */}
      {step === 'type' && (
        <div className="flex-1 p-4 flex flex-col">
          <div className="signal-grid">
            {SIGNAL_TYPES.map((type) => (
              <button
                key={type.id}
                onClick={() => handleTypeSelect(type)}
                className="signal-type-card group"
                data-testid={`type-${type.id}`}
              >
                <div className="signal-type-icon-clean transition-transform group-active:scale-90">
                  {type.isCustomPng ? (
                    <img 
                      src={type.iconPath} 
                      alt={type.labelUa}
                      className="signal-icon-image"
                    />
                  ) : (
                    <type.iconComponent size={80} />
                  )}
                </div>
              </button>
            ))}
          </div>
          
          {/* Info Block */}
          <div className="mt-auto pt-6 px-2">
            <div className="bg-surface rounded-2xl p-4 text-center">
              <p className="text-sm text-neutral-600 leading-relaxed mb-3">
                <span className="block font-medium text-neutral-800 mb-1">Повідомте про подію поруч.</span>
                Ваш сигнал допомагає системі бачити ситуацію в місті.
              </p>
              <div className="flex items-center justify-center gap-4 text-xs text-neutral-500">
                <span className="flex items-center gap-1">
                  <span className="text-success">✓</span> отримуйте XP
                </span>
                <span className="flex items-center gap-1">
                  <span className="text-success">✓</span> рівень довіри
                </span>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Step 2: Create Signal (Location + Photo + Description) */}
      {step === 'create' && (
        <div className="flex-1 p-4 overflow-y-auto">
          {/* Signal Type Header */}
          <div className="flex items-center gap-4 mb-6">
            <div 
              className="w-16 h-16 rounded-2xl flex items-center justify-center flex-shrink-0"
              style={{ background: `${selectedType?.color}15` }}
            >
              {selectedType?.isCustomPng ? (
                <img 
                  src={selectedType.iconPath} 
                  alt={selectedType.labelUa}
                  width={48} 
                  height={48}
                  style={{ objectFit: 'contain' }}
                />
              ) : (
                selectedType?.iconComponent && <selectedType.iconComponent size={48} />
              )}
            </div>
            <div>
              <h2 className="text-lg font-semibold text-neutral-900">{selectedType?.labelUa}</h2>
              <p className="text-sm text-neutral-500">Створення сигналу</p>
            </div>
          </div>
          
          {/* Location Block */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-neutral-700 mb-2">
              <MapPin size={16} className="inline mr-1.5" />
              Локація
            </label>
            <button
              onClick={() => setShowMapPicker(true)}
              className="w-full p-4 bg-surface rounded-2xl flex items-center justify-between active:scale-[0.99] transition-transform"
              data-testid="location-btn"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-primary/10 rounded-xl flex items-center justify-center">
                  {locating ? (
                    <Loader2 size={20} className="text-primary animate-spin" />
                  ) : (
                    <MapPin size={20} className="text-primary" />
                  )}
                </div>
                <div className="text-left">
                  <div className="font-medium text-neutral-900">
                    {location ? 'Моя локація' : 'Визначення...'}
                  </div>
                  {location && (
                    <div className="text-xs text-neutral-500 font-mono">
                      {location.lat.toFixed(4)}, {location.lng.toFixed(4)}
                    </div>
                  )}
                </div>
              </div>
              <span className="text-xs text-primary font-medium">Змінити</span>
            </button>
            <p className="text-xs text-neutral-400 mt-2 px-1">
              Локація використовується тільки для сигналу
            </p>
          </div>
          
          {/* Photo Block */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-neutral-700 mb-2">
              <Camera size={16} className="inline mr-1.5" />
              Фото
              <span className="text-neutral-400 font-normal ml-1">(необов'язково)</span>
            </label>
            
            {photoPreview ? (
              <div className="relative">
                <img 
                  src={photoPreview} 
                  alt="Preview" 
                  className="w-full h-48 object-cover rounded-2xl"
                  data-testid="photo-preview"
                />
                <div className="absolute top-2 right-2 flex gap-2">
                  <button
                    onClick={openCamera}
                    className="w-10 h-10 bg-white/90 backdrop-blur rounded-full flex items-center justify-center shadow-lg active:scale-95"
                    data-testid="retake-btn"
                  >
                    <RefreshCw size={18} className="text-neutral-700" />
                  </button>
                  <button
                    onClick={removePhoto}
                    className="w-10 h-10 bg-white/90 backdrop-blur rounded-full flex items-center justify-center shadow-lg active:scale-95"
                    data-testid="remove-photo-btn"
                  >
                    <X size={18} className="text-neutral-700" />
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={openCamera}
                className="w-full p-6 bg-surface rounded-2xl border-2 border-dashed border-neutral-200 flex flex-col items-center justify-center gap-3 active:scale-[0.99] transition-transform hover:border-primary/30"
                data-testid="take-photo-btn"
              >
                <div className="w-14 h-14 bg-primary/10 rounded-full flex items-center justify-center">
                  <Camera size={24} className="text-primary" />
                </div>
                <div className="text-center">
                  <div className="font-medium text-neutral-900">Зробити фото</div>
                  <div className="text-xs text-neutral-500 mt-0.5">
                    Фото допомагає підтвердити сигнал
                  </div>
                </div>
              </button>
            )}
          </div>
          
          {/* Description Block */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-neutral-700 mb-2">
              <Image size={16} className="inline mr-1.5" />
              Деталі
              <span className="text-neutral-400 font-normal ml-1">(необов'язково)</span>
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Опишіть ситуацію..."
              rows={3}
              className="w-full p-4 bg-surface rounded-2xl text-neutral-900 placeholder:text-neutral-400 focus:outline-none focus:ring-2 focus:ring-primary/20 resize-none"
              data-testid="description-input"
            />
          </div>
          
          {/* Submit Button */}
          <button
            onClick={handleSubmit}
            disabled={loading || !location}
            className="w-full py-4 bg-primary text-white rounded-2xl font-semibold flex items-center justify-center gap-3 shadow-lg shadow-primary/20 active:scale-[0.98] transition-transform disabled:opacity-60"
            data-testid="submit-btn"
          >
            {loading ? (
              <>
                <Loader2 size={20} className="animate-spin" />
                Надсилання...
              </>
            ) : (
              <>
                <Send size={20} />
                Відправити сигнал
              </>
            )}
          </button>
        </div>
      )}
      
      {/* Map Picker Modal */}
      <MapPickerModal
        isOpen={showMapPicker}
        onClose={() => setShowMapPicker(false)}
        onSelect={handleMapSelect}
        initialCenter={location ? [location.lat, location.lng] : userLocation ? [userLocation.lat, userLocation.lng] : [50.4501, 30.5234]}
      />
    </div>
  );
}
