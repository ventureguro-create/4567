/**
 * Signal Toast - Notification for nearby signals
 */
import { useEffect, useState } from 'react';
import { MapPin, X } from 'lucide-react';
import { SIGNAL_TYPES } from '../lib/signalTypes';
import { vibrate } from '../lib/telegram';

export default function SignalToast({ signal, onClose, onView }) {
  const [hiding, setHiding] = useState(false);
  
  const signalType = SIGNAL_TYPES.find(t => t.id === signal?.type);
  const Icon = signalType?.iconComponent;
  const color = signalType?.color || '#3B82F6';
  
  // Auto-hide after 5 seconds
  useEffect(() => {
    const timer = setTimeout(() => {
      handleClose();
    }, 5000);
    
    return () => clearTimeout(timer);
  }, []);
  
  const handleClose = () => {
    setHiding(true);
    setTimeout(onClose, 300);
  };
  
  const handleView = () => {
    vibrate('light');
    onView?.(signal);
    handleClose();
  };
  
  if (!signal) return null;
  
  return (
    <div className={`signal-toast ${hiding ? 'hiding' : ''}`} data-testid="signal-toast">
      <div 
        className="signal-toast-icon"
        style={{ background: `${color}15` }}
      >
        {Icon && <Icon size={24} style={{ color }} />}
      </div>
      
      <div className="signal-toast-content">
        <div className="signal-toast-subtitle flex items-center gap-1">
          <MapPin size={12} />
          <span>{signal.distance || '~200м'}</span>
        </div>
      </div>
      
      <button 
        className="signal-toast-action"
        onClick={handleView}
      >
        Дивитись
      </button>
      
      <button
        onClick={handleClose}
        className="p-2 text-neutral-400 hover:text-neutral-600 transition-colors"
      >
        <X size={18} />
      </button>
    </div>
  );
}
