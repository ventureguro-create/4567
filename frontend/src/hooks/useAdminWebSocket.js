/**
 * useAdminWebSocket - STEP 0.5
 * 
 * WebSocket hook for admin real-time updates.
 * Only invalidation, no data streaming.
 */

import { useEffect, useCallback } from 'react';
import { connectAdminWS, ADMIN_EVENTS } from '../api/adminWs';
import { useAdminStateStore } from '../store/adminState.store';
import { useAdminMetricsStore } from '../store/adminMetrics.store';
import { 
  fetchMLState, 
  fetchProvidersState, 
  fetchRetrainState 
} from '../api/adminState.api';

export function useAdminWebSocket() {
  const updateMLState = useAdminStateStore((s) => s.updateMLState);
  const updateProvidersState = useAdminStateStore((s) => s.updateProvidersState);
  const updateRetrainState = useAdminStateStore((s) => s.updateRetrainState);
  const invalidateMetrics = useAdminMetricsStore((s) => s.invalidate);

  const handleEvent = useCallback(async (eventType, meta) => {
    console.log('[AdminWS] Event:', eventType, meta);
    
    switch (eventType) {
      case ADMIN_EVENTS.ML_STATUS_CHANGED:
      case ADMIN_EVENTS.CIRCUIT_BREAKER_OPENED:
      case ADMIN_EVENTS.CIRCUIT_BREAKER_CLOSED:
        // Refetch ML state
        try {
          const ml = await fetchMLState();
          updateMLState(ml);
        } catch (err) {
          console.error('[AdminWS] Failed to refetch ML state:', err);
        }
        break;
        
      case ADMIN_EVENTS.PROVIDER_COOLDOWN:
        // Refetch providers state
        try {
          const providers = await fetchProvidersState();
          updateProvidersState(providers);
        } catch (err) {
          console.error('[AdminWS] Failed to refetch providers state:', err);
        }
        break;
        
      case ADMIN_EVENTS.RETRAIN_STARTED:
      case ADMIN_EVENTS.RETRAIN_FINISHED:
        // Refetch retrain state
        try {
          const retrain = await fetchRetrainState();
          updateRetrainState(retrain);
        } catch (err) {
          console.error('[AdminWS] Failed to refetch retrain state:', err);
        }
        // Also invalidate metrics (accuracy may change)
        invalidateMetrics();
        break;
        
      case ADMIN_EVENTS.DRIFT_DETECTED:
        // Invalidate metrics (drift affects accuracy display)
        invalidateMetrics();
        break;
        
      case ADMIN_EVENTS.SETTINGS_CHANGED:
        // Could refetch system state if needed
        break;
        
      default:
        break;
    }
  }, [updateMLState, updateProvidersState, updateRetrainState, invalidateMetrics]);

  useEffect(() => {
    const cleanup = connectAdminWS(handleEvent);
    return cleanup;
  }, [handleEvent]);
}
