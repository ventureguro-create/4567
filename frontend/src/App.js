import "./App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Suspense, lazy } from "react";

// Loading component
const PageLoader = () => (
  <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--tg-theme-bg-color, #ffffff)' }}>
    <div className="flex flex-col items-center gap-4">
      <div className="w-10 h-10 border-4 border-gray-200 rounded-full animate-spin" style={{ borderTopColor: 'var(--tg-theme-button-color, #3390ec)' }} />
      <p className="text-sm font-medium" style={{ color: 'var(--tg-theme-hint-color, #999999)' }}>Loading...</p>
    </div>
  </div>
);

// Telegram Mini App - Main interface
const MiniApp = lazy(() => import("./miniapp/MiniApp"));

// Geo Admin - separate protected admin panel
const GeoAdminPage = lazy(() => import("./pages/GeoAdminPage"));

// Map Picker - Telegram WebApp for location selection (legacy)
const MapPickerPage = lazy(() => import("./pages/MapPickerPage"));

// Legacy RadarPage for reference (keep for admin use)
const RadarPageLegacy = lazy(() => import("./pages/RadarPage"));

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Telegram Mini App - Main interface */}
          <Route path="/" element={<MiniApp />} />
          <Route path="/app" element={<MiniApp />} />
          <Route path="/app/*" element={<MiniApp />} />
          
          {/* Geo Admin - separate protected route */}
          <Route path="/geo-admin" element={<GeoAdminPage />} />
          <Route path="/geo-admin/*" element={<GeoAdminPage />} />
          
          {/* Legacy pages (for admin/testing) */}
          <Route path="/legacy/radar" element={<RadarPageLegacy />} />
          <Route path="/map-picker" element={<MapPickerPage />} />
          
          <Route path="/*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  );
}

export default App;
