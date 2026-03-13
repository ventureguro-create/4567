/**
 * Alerts Page - Modern Signal Feed with Confirm/Reject
 */
import { useEffect } from 'react';
import { Check, X, Clock, MapPin, Loader2 } from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { vibrate } from '../lib/telegram';
import { SIGNAL_TYPES, getSignalColor } from '../lib/signalTypes';
import { formatDistanceToNow } from 'date-fns';
import { uk } from 'date-fns/locale';

export default function AlertsPage() {
  const { 
    alerts, 
    alertsLoading, 
    fetchAlerts, 
    voteSignal,
    nearbySignals,
    fetchNearbySignals,
    userLocation
  } = useAppStore();
  
  useEffect(() => {
    fetchAlerts();
    if (userLocation) {
      fetchNearbySignals();
    }
  }, [fetchAlerts, fetchNearbySignals, userLocation]);
  
  const handleVote = async (signalId, vote) => {
    vibrate('medium');
    const result = await voteSignal(signalId, vote);
    if (result.ok) {
      vibrate('success');
      fetchAlerts();
      fetchNearbySignals();
    } else {
      vibrate('error');
    }
  };
  
  const displayItems = nearbySignals.length > 0 ? nearbySignals : alerts;
  
  const getDistance = (signal) => {
    if (!userLocation || !signal.lat || !signal.lng) return null;
    
    const R = 6371000;
    const dLat = (signal.lat - userLocation.lat) * Math.PI / 180;
    const dLon = (signal.lng - userLocation.lng) * Math.PI / 180;
    const a = 
      Math.sin(dLat/2) * Math.sin(dLat/2) +
      Math.cos(userLocation.lat * Math.PI / 180) * Math.cos(signal.lat * Math.PI / 180) *
      Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const d = R * c;
    
    if (d < 1000) return `${Math.round(d)}м`;
    return `${(d / 1000).toFixed(1)}км`;
  };
  
  const formatTime = (dateString) => {
    try {
      return formatDistanceToNow(new Date(dateString), { addSuffix: true, locale: uk });
    } catch {
      return 'нещодавно';
    }
  };
  
  return (
    <div className="h-full flex flex-col bg-background pb-[80px]" data-testid="alerts-page">
      {/* Header */}
      <div className="flex items-center justify-between p-4 bg-surface">
        <h1 className="text-lg font-semibold text-neutral-900">Сигнали</h1>
        <span className="px-3 py-1 bg-neutral-100 rounded-full text-xs font-medium text-neutral-600">
          {displayItems.length} активних
        </span>
      </div>
      
      {/* Content */}
      {alertsLoading && displayItems.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center">
          <Loader2 size={32} className="animate-spin text-primary mb-3" />
          <span className="text-neutral-500">Завантаження...</span>
        </div>
      ) : displayItems.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <div className="w-16 h-16 bg-neutral-100 rounded-full flex items-center justify-center mb-4">
            <MapPin size={32} className="text-neutral-400" />
          </div>
          <h3 className="text-lg font-semibold text-neutral-900 mb-1">Сигналів немає</h3>
          <p className="text-sm text-neutral-500">Увімкніть радар щоб бачити сигнали поруч</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto no-scrollbar p-4 space-y-3">
          {displayItems.map((signal) => {
            const signalType = SIGNAL_TYPES.find(t => t.id === signal.type);
            const Icon = signalType?.iconComponent;
            const color = signalType?.color || '#64748B';
            
            return (
              <div 
                key={signal.id || signal._id} 
                className="glass-card-solid p-4 animate-fade-in"
                data-testid={`alert-${signal.id || signal._id}`}
              >
                <div className="flex items-start gap-4">
                  {/* Icon */}
                  <div 
                    className="w-12 h-12 rounded-xl flex items-center justify-center flex-shrink-0"
                    style={{ background: `${color}15` }}
                  >
                    {Icon && <Icon size={24} style={{ color }} />}
                  </div>
                  
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span 
                        className="px-2 py-0.5 rounded-full text-xs font-medium"
                        style={{ 
                          background: `${color}15`,
                          color: color 
                        }}
                      >
                        {Math.round((signal.confidence || 0.5) * 100)}%
                      </span>
                    </div>
                    
                    <div className="flex items-center gap-3 text-xs text-neutral-500 mb-2">
                      {getDistance(signal) && (
                        <span className="flex items-center gap-1">
                          <MapPin size={12} />
                          {getDistance(signal)}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Clock size={12} />
                        {formatTime(signal.createdAt || signal.created_at)}
                      </span>
                    </div>
                    
                    {signal.description && (
                      <p className="text-sm text-neutral-600 line-clamp-2">
                        {signal.description}
                      </p>
                    )}
                  </div>
                </div>
                
                {/* Actions */}
                <div className="flex gap-2 mt-4 pt-4 border-t border-neutral-100">
                  <button 
                    onClick={() => handleVote(signal.id || signal._id, 'confirm')}
                    className="flex-1 py-2.5 bg-success/10 text-success rounded-xl font-medium flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
                    data-testid={`confirm-${signal.id || signal._id}`}
                  >
                    <Check size={18} />
                    Є
                  </button>
                  <button 
                    onClick={() => handleVote(signal.id || signal._id, 'reject')}
                    className="flex-1 py-2.5 bg-alert/10 text-alert rounded-xl font-medium flex items-center justify-center gap-2 active:scale-[0.98] transition-transform"
                    data-testid={`reject-${signal.id || signal._id}`}
                  >
                    <X size={18} />
                    Немає
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
