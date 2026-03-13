/**
 * Telegram Mini App - Main Component
 */
import { useEffect } from 'react';
import { useAppStore } from './stores/appStore';
import { initTelegramSDK, getTelegramUser, isTelegramWebApp } from './lib/telegram';
import BottomNav from './components/BottomNav';
import RadarPage from './pages/RadarPage';
import ReportPage from './pages/ReportPage';
import AlertsPage from './pages/AlertsPage';
import ProfilePage from './pages/ProfilePage';
import './MiniApp.css';

export default function MiniApp() {
  const { activeTab, setTelegramUser } = useAppStore();
  
  // Initialize Telegram SDK
  useEffect(() => {
    // Initialize SDK
    initTelegramSDK();
    
    // Get Telegram user
    const user = getTelegramUser();
    if (user) {
      setTelegramUser(user);
    }
    
    // Check if not in Telegram (development mode)
    if (!isTelegramWebApp()) {
      console.log('Not running inside Telegram - development mode');
      // Set mock user for development
      setTelegramUser({
        id: 12345678,
        firstName: 'Dev',
        lastName: 'User',
        username: 'devuser',
      });
    }
  }, [setTelegramUser]);
  
  // Render active page
  const renderPage = () => {
    switch (activeTab) {
      case 'radar':
        return <RadarPage />;
      case 'report':
        return <ReportPage />;
      case 'alerts':
        return <AlertsPage />;
      case 'profile':
        return <ProfilePage />;
      default:
        return <RadarPage />;
    }
  };
  
  return (
    <div className="mini-app" data-testid="mini-app">
      <main className="mini-app-content">
        {renderPage()}
      </main>
      <BottomNav />
    </div>
  );
}
