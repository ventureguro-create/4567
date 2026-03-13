/**
 * useRealtimeWatchlist Hook (P2.1)
 * 
 * Polling engine for real-time watchlist monitoring:
 * - 30s interval polling
 * - Pause on tab blur
 * - Instant refresh on focus
 * - Manual refresh support
 * 
 * Principles:
 * - No WebSocket
 * - Observation only
 * - User-controlled
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import * as watchlistApi from '../api/watchlist.api';

// Polling configuration
const POLL_INTERVAL = 30 * 1000; // 30 seconds
const INITIAL_WINDOW = 5 * 60 * 1000; // 5 minutes for first load

/**
 * Real-time watchlist monitoring hook
 */
export function useRealtimeWatchlist(options = {}) {
  const {
    enabled = true,
    pollInterval = POLL_INTERVAL,
    onNewActivity = null,
  } = options;

  // State
  const [summary, setSummary] = useState({
    newEvents: 0,
    newAlerts: 0,
    newMigrations: 0,
    updatedActors: 0,
    lastUpdateAt: null,
  });
  const [isPolling, setIsPolling] = useState(false);
  const [lastFetch, setLastFetch] = useState(null);
  const [error, setError] = useState(null);
  
  // Refs
  const pollTimeoutRef = useRef(null);
  const lastFetchRef = useRef(null);
  const isVisibleRef = useRef(true);

  // Fetch realtime summary
  const fetchSummary = useCallback(async () => {
    if (!enabled) return;
    
    try {
      setIsPolling(true);
      setError(null);
      
      const response = await watchlistApi.getRealtimeSummary(5);
      
      if (response?.ok) {
        const newSummary = {
          newEvents: response.newEvents || 0,
          newAlerts: response.newAlerts || 0,
          newMigrations: response.newMigrations || 0,
          updatedActors: response.updatedActors || 0,
          lastUpdateAt: response.lastUpdateAt || new Date().toISOString(),
        };
        
        setSummary(prev => {
          // Check if there's new activity
          const hasNewActivity = 
            newSummary.newEvents > prev.newEvents ||
            newSummary.newAlerts > prev.newAlerts ||
            newSummary.newMigrations > prev.newMigrations;
          
          if (hasNewActivity && onNewActivity) {
            onNewActivity(newSummary);
          }
          
          return newSummary;
        });
        
        setLastFetch(new Date());
        lastFetchRef.current = new Date();
      }
    } catch (err) {
      console.error('[Realtime] Fetch error:', err);
      setError('Failed to fetch updates');
    } finally {
      setIsPolling(false);
    }
  }, [enabled, onNewActivity]);

  // Schedule next poll
  const schedulePoll = useCallback(() => {
    if (pollTimeoutRef.current) {
      clearTimeout(pollTimeoutRef.current);
    }
    
    if (!enabled || !isVisibleRef.current) return;
    
    pollTimeoutRef.current = setTimeout(() => {
      fetchSummary();
      schedulePoll();
    }, pollInterval);
  }, [enabled, pollInterval, fetchSummary]);

  // Manual refresh
  const refresh = useCallback(() => {
    fetchSummary();
  }, [fetchSummary]);

  // Handle visibility change
  useEffect(() => {
    const handleVisibilityChange = () => {
      const isVisible = document.visibilityState === 'visible';
      isVisibleRef.current = isVisible;
      
      if (isVisible) {
        // Tab became visible - fetch immediately
        fetchSummary();
        schedulePoll();
      } else {
        // Tab hidden - pause polling
        if (pollTimeoutRef.current) {
          clearTimeout(pollTimeoutRef.current);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [fetchSummary, schedulePoll]);

  // Start polling on mount
  useEffect(() => {
    if (!enabled) return;
    
    // Initial fetch
    fetchSummary();
    
    // Start polling
    schedulePoll();
    
    return () => {
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current);
      }
    };
  }, [enabled, fetchSummary, schedulePoll]);

  // Total new count for badge
  const totalNew = summary.newEvents + summary.newAlerts;
  const hasNewActivity = totalNew > 0;

  return {
    summary,
    isPolling,
    lastFetch,
    error,
    refresh,
    totalNew,
    hasNewActivity,
  };
}

/**
 * Hook for fetching delta changes
 */
export function useEventChanges(since, options = {}) {
  const { limit = 50, enabled = true } = options;
  
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchChanges = useCallback(async () => {
    if (!enabled) return;
    
    try {
      setLoading(true);
      setError(null);
      
      const response = await watchlistApi.getEventChanges(
        since || new Date(Date.now() - INITIAL_WINDOW).toISOString(),
        limit
      );
      
      if (response?.ok) {
        setData(response);
      } else {
        setError(response?.error || 'Failed to fetch changes');
      }
    } catch (err) {
      setError('Failed to fetch changes');
    } finally {
      setLoading(false);
    }
  }, [since, limit, enabled]);

  useEffect(() => {
    fetchChanges();
  }, [fetchChanges]);

  return {
    data,
    loading,
    error,
    refetch: fetchChanges,
  };
}

export default useRealtimeWatchlist;
