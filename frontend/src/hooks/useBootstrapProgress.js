/**
 * useBootstrapProgress Hook (P2.1 Step 3)
 * 
 * Unified polling hook for bootstrap task progress.
 * Features:
 * - Auto-polling every 5 seconds
 * - Auto-stop when done/failed
 * - Callback on completion
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import bootstrapApi from '../api/bootstrap.api';

const POLL_INTERVAL = 5000; // 5 seconds

/**
 * Hook for polling bootstrap task progress
 * 
 * @param {string} dedupKey - The task dedupKey to poll
 * @param {boolean} enabled - Whether polling is enabled
 * @param {Function} onComplete - Callback when task completes (done/failed)
 * @returns {Object} { status, progress, step, etaSeconds, isPolling, error }
 */
export function useBootstrapProgress(dedupKey, enabled = true, onComplete = null) {
  const [state, setState] = useState({
    status: null,
    progress: 0,
    step: null,
    etaSeconds: null,
    attempts: 0,
    updatedAt: null,
    exists: false,
  });
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState(null);
  
  const intervalRef = useRef(null);
  const onCompleteRef = useRef(onComplete);
  
  // Keep callback ref updated
  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const fetchStatus = useCallback(async () => {
    if (!dedupKey) return;
    
    try {
      const data = await bootstrapApi.getStatus(dedupKey);
      
      if (data) {
        setState({
          status: data.status,
          progress: data.progress || 0,
          step: data.step,
          etaSeconds: data.etaSeconds,
          attempts: data.attempts || 0,
          updatedAt: data.updatedAt,
          exists: data.exists,
        });
        
        // Stop polling and trigger callback when done/failed
        if (data.status === 'done' || data.status === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
          }
          setIsPolling(false);
          
          if (onCompleteRef.current) {
            onCompleteRef.current(data.status);
          }
        }
      }
      
      setError(null);
    } catch (err) {
      console.error('[useBootstrapProgress] Poll error:', err);
      setError(err.message || 'Failed to fetch status');
    }
  }, [dedupKey]);

  useEffect(() => {
    if (!enabled || !dedupKey) {
      setIsPolling(false);
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    // Initial fetch
    fetchStatus();
    setIsPolling(true);

    // Start polling
    intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setIsPolling(false);
    };
  }, [dedupKey, enabled, fetchStatus]);

  return {
    ...state,
    isPolling,
    error,
    refetch: fetchStatus,
  };
}

/**
 * Format ETA seconds to human readable string
 */
export function formatETA(etaSeconds) {
  if (etaSeconds === null || etaSeconds === undefined) return null;
  
  if (etaSeconds < 60) {
    return `~${etaSeconds}s`;
  } else if (etaSeconds < 3600) {
    const minutes = Math.ceil(etaSeconds / 60);
    return `~${minutes} min`;
  } else {
    const hours = Math.ceil(etaSeconds / 3600);
    return `~${hours}h`;
  }
}

/**
 * Format step name to human readable
 */
export function formatStepName(step) {
  if (!step) return 'Initializing...';
  
  const stepNames = {
    'erc20_indexer': 'Scanning transactions',
    'build_transfers': 'Building transfers',
    'build_relations': 'Analyzing relationships',
    'build_bundles': 'Grouping activity',
    'build_signals': 'Generating signals',
    'build_scores': 'Calculating scores',
    'build_strategy_profiles': 'Classifying strategies',
    'token_metadata': 'Fetching token info',
    'erc20_indexer_by_token': 'Scanning token transfers',
    'market_metrics': 'Loading market data',
    'token_signals': 'Analyzing token activity',
    'basic_indexer': 'Basic indexing',
  };
  
  return stepNames[step] || step.replace(/_/g, ' ');
}

export default useBootstrapProgress;
