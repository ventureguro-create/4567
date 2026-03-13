/**
 * Telegram Mini App SDK initialization
 */
let initialized = false;

// Check if running inside Telegram
export function isTelegramWebApp() {
  return typeof window !== 'undefined' && window.Telegram?.WebApp;
}

export async function initTelegramSDK(debug = false) {
  if (initialized) return;
  
  // If not in Telegram, skip SDK initialization
  if (!isTelegramWebApp()) {
    console.log('Not running inside Telegram - development mode');
    initialized = true;
    return;
  }
  
  try {
    // Dynamic import to avoid errors outside Telegram
    const { 
      init: initSDK,
      backButton,
      miniApp,
      themeParams,
      viewport,
      initData,
    } = await import('@telegram-apps/sdk-react');
    
    // Initialize SDK
    initSDK();
    
    // Mount components
    if (backButton.isSupported()) {
      backButton.mount();
    }
    
    if (miniApp.mount.isAvailable()) {
      miniApp.mount();
    }
    
    if (themeParams.mount.isAvailable()) {
      themeParams.mount();
    }
    
    // Initialize viewport
    if (viewport.mount.isAvailable()) {
      viewport.mount()
        .then(() => {
          viewport.bindCssVars();
          if (miniApp.bindCssVars.isAvailable()) {
            miniApp.bindCssVars();
          }
          if (themeParams.bindCssVars.isAvailable()) {
            themeParams.bindCssVars();
          }
          // Expand to full height
          if (viewport.expand.isAvailable()) {
            viewport.expand();
          }
        })
        .catch(console.error);
    }
    
    // Restore init data
    if (initData.restore.isAvailable()) {
      initData.restore();
    }
    
    console.log('Telegram SDK initialized');
    
  } catch (e) {
    console.error('Failed to initialize Telegram SDK:', e);
  }
  
  initialized = true;
}

/**
 * Get current user from Telegram
 */
export function getTelegramUser() {
  try {
    if (isTelegramWebApp() && window.Telegram?.WebApp?.initDataUnsafe?.user) {
      return window.Telegram.WebApp.initDataUnsafe.user;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Get init data for backend validation
 */
export function getInitData() {
  try {
    if (isTelegramWebApp() && window.Telegram?.WebApp?.initData) {
      return window.Telegram.WebApp.initData;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Haptic feedback
 */
export function vibrate(type = 'light') {
  try {
    if (isTelegramWebApp() && window.Telegram?.WebApp?.HapticFeedback) {
      const intensity = type === 'success' ? 'medium' : type === 'error' ? 'heavy' : type;
      window.Telegram.WebApp.HapticFeedback.impactOccurred(intensity);
    }
  } catch {
    // Silently fail if not available
  }
}

/**
 * Request location
 */
export async function requestLocation() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation not supported'));
      return;
    }
    
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracy: position.coords.accuracy
        });
      },
      (error) => {
        reject(error);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000
      }
    );
  });
}

/**
 * Close Mini App
 */
export function closeMiniApp() {
  try {
    if (isTelegramWebApp() && window.Telegram?.WebApp?.close) {
      window.Telegram.WebApp.close();
    }
  } catch {
    // Silently fail
  }
}
