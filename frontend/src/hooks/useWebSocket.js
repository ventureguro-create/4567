/**
 * useWebSocket Hook (P2.3)
 * 
 * Universal WebSocket hook for real-time updates.
 * Features:
 * - Auto-reconnect
 * - Subscription filtering
 * - Fallback to polling on disconnect
 * - Typed events
 */
import { useState, useEffect, useCallback, useRef } from 'react';

// Event types
export type EventType = 
  | 'bootstrap.progress'
  | 'bootstrap.done'
  | 'bootstrap.failed'
  | 'resolver.updated'
  | 'attribution.confirmed'
  | 'alert.new'
  | 'signal.new';

export type SubscriptionCategory = 'bootstrap' | 'resolver' | 'attribution' | 'alerts' | 'signals';

// WebSocket URL - derive from REACT_APP_BACKEND_URL
const getWsUrl = () => {
  const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
  if (backendUrl) {
    // Convert http(s) to ws(s) and add /ws path (ws-gateway.ts endpoint)
    return backendUrl.replace(/^http/, 'ws') + '/ws';
  }
  // Fallback for local development
  return (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
    window.location.host + '/ws';
};

const WS_URL = getWsUrl();

// Reconnect config
const RECONNECT_DELAY = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

/**
 * WebSocket hook
 */
export function useWebSocket({
  subscriptions = [],
  onEvent,
  enabled = true,
}) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeoutRef = useRef(null);
  const onEventRef = useRef(onEvent);

  // Keep callback ref updated
  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  const connect = useCallback(() => {
    if (!enabled) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      console.log('[WS] Connecting to:', WS_URL);
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] Connected');
        setIsConnected(true);
        setError(null);
        reconnectAttempts.current = 0;

        // Send hello with subscriptions
        ws.send(JSON.stringify({
          type: 'hello',
          subscriptions,
        }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          // Skip connection events
          if (data.type === 'connected' || data.type === 'pong') {
            return;
          }
          
          // Call event handler
          if (onEventRef.current) {
            onEventRef.current(data);
          }
        } catch (err) {
          console.error('[WS] Message parse error:', err);
        }
      };

      ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        setError('WebSocket error');
      };

      ws.onclose = () => {
        console.log('[WS] Disconnected');
        setIsConnected(false);
        wsRef.current = null;

        // Auto-reconnect
        if (enabled && reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++;
          console.log(`[WS] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts.current})`);
          
          reconnectTimeoutRef.current = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        }
      };
    } catch (err) {
      console.error('[WS] Connection error:', err);
      setError(err.message);
    }
  }, [enabled, subscriptions]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
  }, []);

  // Connect on mount
  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [enabled, connect, disconnect]);

  // Send message
  const send = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Subscribe to category
  const subscribe = useCallback((category) => {
    send({ type: 'subscribe', category });
  }, [send]);

  // Unsubscribe from category
  const unsubscribe = useCallback((category) => {
    send({ type: 'unsubscribe', category });
  }, [send]);

  return {
    isConnected,
    error,
    send,
    subscribe,
    unsubscribe,
    reconnect: connect,
  };
}

/**
 * Hook for bootstrap progress with WebSocket
 */
export function useBootstrapProgressWS(dedupKey, enabled = true, onComplete = null) {
  const [progress, setProgress] = useState(0);
  const [step, setStep] = useState(null);
  const [eta, setEta] = useState(null);
  const [status, setStatus] = useState('queued');
  const onCompleteRef = useRef(onComplete);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  const handleEvent = useCallback((event) => {
    // Filter by dedupKey
    if (event.dedupKey !== dedupKey) return;

    switch (event.type) {
      case 'bootstrap.progress':
        setProgress(event.progress);
        setStep(event.step);
        setEta(event.eta);
        setStatus('running');
        break;
      
      case 'bootstrap.done':
        setProgress(100);
        setStatus('done');
        if (onCompleteRef.current) {
          onCompleteRef.current('done');
        }
        break;
      
      case 'bootstrap.failed':
        setStatus('failed');
        if (onCompleteRef.current) {
          onCompleteRef.current('failed');
        }
        break;
    }
  }, [dedupKey]);

  const { isConnected, error } = useWebSocket({
    subscriptions: ['bootstrap'],
    onEvent: handleEvent,
    enabled: enabled && !!dedupKey,
  });

  return {
    progress,
    step,
    eta,
    status,
    isConnected,
    error,
    // Fallback needed if WS not connected
    needsFallback: !isConnected,
  };
}

export default useWebSocket;
