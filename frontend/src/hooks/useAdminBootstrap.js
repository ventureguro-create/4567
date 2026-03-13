/**
 * useAdminBootstrap - STEP 0.5
 * 
 * Bootstrap hook for admin panel.
 * FAST PATH: state first, metrics async.
 */

import { useEffect, useRef } from 'react';
import { fetchAdminState } from '../api/adminState.api';
import { fetchAdminMetrics } from '../api/adminMetrics.api';
import { useAdminStateStore } from '../store/adminState.store';
import { useAdminMetricsStore } from '../store/adminMetrics.store';

export function useAdminBootstrap() {
  const mounted = useRef(true);
  
  const { 
    setState, 
    setLoading: setStateLoading, 
    setError: setStateError,
    state,
  } = useAdminStateStore();
  
  const { 
    setMetrics, 
    setLoading: setMetricsLoading,
    metrics,
    isStale,
  } = useAdminMetricsStore();

  useEffect(() => {
    mounted.current = true;
    
    async function bootstrap() {
      // Skip if already loaded
      if (state) return;
      
      setStateLoading(true);

      try {
        // 🔥 FAST PATH — блокирует рендер
        const stateData = await fetchAdminState();
        if (!mounted.current) return;
        setState(stateData);
        
      } catch (err) {
        if (!mounted.current) return;
        setStateError(err.message);
        console.error('[AdminBootstrap] State fetch failed:', err);
      }

      // 🟡 SLOW PATH — НЕ блокирует UI
      if (!metrics || isStale()) {
        setMetricsLoading(true);
        fetchAdminMetrics()
          .then((data) => {
            if (mounted.current) setMetrics(data);
          })
          .catch((err) => {
            console.error('[AdminBootstrap] Metrics fetch failed:', err);
          });
      }
    }

    bootstrap();
    
    return () => { 
      mounted.current = false; 
    };
  }, []);
  
  return {
    isLoading: useAdminStateStore((s) => s.loading),
    hasError: useAdminStateStore((s) => !!s.error),
    error: useAdminStateStore((s) => s.error),
  };
}
