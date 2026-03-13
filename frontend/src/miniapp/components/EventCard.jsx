/**
 * EventCard Component
 * Displays a correlated event with confirm/not-there actions
 */
import React from 'react';
import { useAppStore } from '../stores/appStore';
import { SIGNAL_TYPES } from '../lib/signalTypes';

// Status badge colors
const STATUS_COLORS = {
  candidate: 'bg-yellow-500/20 text-yellow-400',
  correlated: 'bg-blue-500/20 text-blue-400',
  verified: 'bg-green-500/20 text-green-400',
  expired: 'bg-gray-500/20 text-gray-400',
  dismissed: 'bg-red-500/20 text-red-400',
};

// Strength indicators
const STRENGTH_ICONS = {
  weak: '●',
  medium: '●●',
  strong: '●●●',
  critical: '●●●●',
};

export function EventCard({ event, onClose }) {
  const { confirmEvent, reportNotThere } = useAppStore();
  const [loading, setLoading] = React.useState(false);
  
  // Get signal type config
  const signalConfig = SIGNAL_TYPES.find(s => s.id === event.type) || {
    emoji: '📍',
    title: event.type,
    color: 'gray'
  };
  
  // Format time ago
  const getTimeAgo = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000 / 60); // minutes
    
    if (diff < 1) return 'Щойно';
    if (diff < 60) return `${diff} хв тому`;
    if (diff < 1440) return `${Math.floor(diff / 60)} год тому`;
    return `${Math.floor(diff / 1440)} дн тому`;
  };
  
  const handleConfirm = async () => {
    setLoading(true);
    await confirmEvent(event.event_id);
    setLoading(false);
    onClose?.();
  };
  
  const handleNotThere = async () => {
    setLoading(true);
    await reportNotThere(event.event_id);
    setLoading(false);
    onClose?.();
  };
  
  return (
    <div 
      className="event-card"
      data-testid={`event-card-${event.event_id}`}
    >
      {/* Header */}
      <div className="event-card-header">
        <div className="event-type-badge" style={{ background: `var(--${signalConfig.color}-500)` }}>
          <span className="event-emoji">{signalConfig.emoji}</span>
          <span className="event-type-title">{signalConfig.title}</span>
        </div>
        
        <span className={`event-status-badge ${STATUS_COLORS[event.status] || ''}`}>
          {event.status}
        </span>
      </div>
      
      {/* Location */}
      <div className="event-location">
        <span className="event-coords">
          {event.lat?.toFixed(4)}, {event.lng?.toFixed(4)}
        </span>
      </div>
      
      {/* Stats */}
      <div className="event-stats">
        <div className="event-stat">
          <span className="event-stat-label">Reports</span>
          <span className="event-stat-value">{event.report_count || 1}</span>
        </div>
        
        <div className="event-stat">
          <span className="event-stat-label">Sources</span>
          <span className="event-stat-value">{event.source_count || 1}</span>
        </div>
        
        <div className="event-stat">
          <span className="event-stat-label">Confidence</span>
          <span className="event-stat-value">{Math.round((event.confidence || 0) * 100)}%</span>
        </div>
      </div>
      
      {/* Strength */}
      <div className="event-strength">
        <span className="event-strength-dots">
          {STRENGTH_ICONS[event.strength] || '●'}
        </span>
        <span className="event-strength-label">{event.strength || 'weak'}</span>
        <span className="event-time">{getTimeAgo(event.updated_at)}</span>
      </div>
      
      {/* Photo indicator */}
      {event.photo_count > 0 && (
        <div className="event-photos">
          📷 {event.photo_count} photo(s)
        </div>
      )}
      
      {/* Actions */}
      <div className="event-actions">
        <button 
          className="event-btn event-btn-confirm"
          onClick={handleConfirm}
          disabled={loading}
          data-testid="event-confirm-btn"
        >
          ✓ Підтверджую
        </button>
        
        <button 
          className="event-btn event-btn-not-there"
          onClick={handleNotThere}
          disabled={loading}
          data-testid="event-not-there-btn"
        >
          ✗ Вже немає
        </button>
      </div>
      
      {/* Negative reports warning */}
      {event.negative_reports > 0 && (
        <div className="event-negative-warning">
          ⚠️ {event.negative_reports} negative report(s)
        </div>
      )}
    </div>
  );
}

// Styles
const styles = `
.event-card {
  background: rgba(30, 30, 40, 0.95);
  border-radius: 16px;
  padding: 16px;
  color: #fff;
  font-size: 14px;
  max-width: 320px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.event-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.event-type-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 20px;
  font-weight: 600;
}

.event-emoji {
  font-size: 18px;
}

.event-status-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  text-transform: uppercase;
}

.event-location {
  color: #888;
  font-size: 12px;
  margin-bottom: 12px;
}

.event-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.event-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.event-stat-label {
  font-size: 10px;
  color: #666;
  text-transform: uppercase;
}

.event-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
}

.event-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  color: #888;
  font-size: 12px;
}

.event-strength-dots {
  color: #4ade80;
  font-size: 10px;
  letter-spacing: 2px;
}

.event-strength-label {
  text-transform: capitalize;
}

.event-time {
  margin-left: auto;
}

.event-photos {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  margin-bottom: 12px;
}

.event-actions {
  display: flex;
  gap: 8px;
}

.event-btn {
  flex: 1;
  padding: 12px;
  border: none;
  border-radius: 10px;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.event-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.event-btn-confirm {
  background: #22c55e;
  color: #fff;
}

.event-btn-confirm:hover:not(:disabled) {
  background: #16a34a;
}

.event-btn-not-there {
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.event-btn-not-there:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.3);
}

.event-negative-warning {
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border-radius: 8px;
  color: #f87171;
  font-size: 12px;
  text-align: center;
}
`;

// Inject styles
if (typeof document !== 'undefined') {
  const styleEl = document.createElement('style');
  styleEl.textContent = styles;
  document.head.appendChild(styleEl);
}

export default EventCard;
