/**
 * Admin Auth Context
 * 
 * Provides authentication state for admin pages.
 */

import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { 
  checkAuthStatus, 
  login as apiLogin, 
  logout as apiLogout,
  getAdminToken,
  setAdminToken,
} from '../api/admin.api';

const AdminAuthContext = createContext(null);

export function AdminAuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(() => getAdminToken());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Check if already authenticated on mount
  useEffect(() => {
    async function checkAuth() {
      const savedToken = getAdminToken();
      if (!savedToken) {
        setLoading(false);
        return;
      }

      try {
        const result = await checkAuthStatus();
        if (result.ok) {
          setUser({
            role: result.data.role,
            userId: result.data.userId,
            expiresAt: result.data.expiresAtTs,
          });
          setToken(savedToken);
        }
      } catch (err) {
        console.log('[AdminAuth] No valid session');
        setToken(null);
      } finally {
        setLoading(false);
      }
    }
    checkAuth();
  }, []);

  const login = useCallback(async (username, password) => {
    setError(null);
    try {
      const result = await apiLogin(username, password);
      if (result.ok) {
        // Save token to localStorage
        setAdminToken(result.token);
        setUser({
          role: result.role,
          username: result.username,
          expiresAt: result.expiresAtTs,
        });
        setToken(result.token);
        return { ok: true };
      }
      return { ok: false, error: 'Login failed' };
    } catch (err) {
      const message = err.message || 'Login failed';
      setError(message);
      return { ok: false, error: message };
    }
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setUser(null);
    setToken(null);
  }, []);

  const isAdmin = user?.role === 'ADMIN';
  const isModerator = user?.role === 'MODERATOR';
  const isAuthenticated = !!user;

  return (
    <AdminAuthContext.Provider
      value={{
        user,
        token,
        loading,
        error,
        login,
        logout,
        isAdmin,
        isModerator,
        isAuthenticated,
      }}
    >
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (!context) {
    throw new Error('useAdminAuth must be used within AdminAuthProvider');
  }
  return context;
}

export default AdminAuthContext;
