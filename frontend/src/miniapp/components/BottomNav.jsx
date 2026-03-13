/**
 * Bottom Navigation - Modern Urban Radar Style
 */
import { MapPin, Plus, Bell, User } from 'lucide-react';
import { useAppStore } from '../stores/appStore';
import { vibrate } from '../lib/telegram';

const tabs = [
  { id: 'radar', icon: MapPin, label: 'Радар' },
  { id: 'report', icon: Plus, label: 'Сигнал' },
  { id: 'alerts', icon: Bell, label: 'Алерти' },
  { id: 'profile', icon: User, label: 'Профіль' },
];

export default function BottomNav() {
  const { activeTab, setActiveTab, unreadAlerts } = useAppStore();
  
  const handleTabClick = (tabId) => {
    vibrate('light');
    setActiveTab(tabId);
  };
  
  return (
    <nav className="bottom-nav-modern" data-testid="bottom-nav">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        
        return (
          <button
            key={tab.id}
            className={`nav-item-modern ${isActive ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
            data-testid={`nav-${tab.id}`}
          >
            <div className="nav-icon-modern relative">
              <Icon size={22} strokeWidth={isActive ? 2.5 : 2} />
              {tab.id === 'alerts' && unreadAlerts > 0 && (
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-alert text-white text-[10px] font-bold rounded-full flex items-center justify-center">
                  {unreadAlerts > 9 ? '9+' : unreadAlerts}
                </span>
              )}
            </div>
            <span className="nav-label-modern">{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
