import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';

const WebSocketContext = createContext(null);

// Connection states
const WS_STATES = {
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  DISCONNECTED: 'disconnected',
  RECONNECTING: 'reconnecting',
};

export function WebSocketProvider({ children }) {
  const [connectionState, setConnectionState] = useState(WS_STATES.DISCONNECTED);
  const [lastMessage, setLastMessage] = useState(null);
  const [transfers, setTransfers] = useState([]);
  const [marketStats, setMarketStats] = useState(null);
  
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const reconnectAttempts = useRef(0);
  const maxReconnectAttempts = 5;
  const subscribedChannels = useRef(new Set());
  
  // Build WebSocket URL from backend URL
  const getWsUrl = useCallback(() => {
    const backendUrl = process.env.REACT_APP_BACKEND_URL || '';
    // Convert http(s) to ws(s)
    const wsProtocol = backendUrl.startsWith('https') ? 'wss' : 'ws';
    const wsHost = backendUrl.replace(/^https?:\/\//, '');
    return `${wsProtocol}://${wsHost}/api/ws`;
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    setConnectionState(WS_STATES.CONNECTING);
    
    try {
      const wsUrl = getWsUrl();
      wsRef.current = new WebSocket(wsUrl);
      
      wsRef.current.onopen = () => {
        console.log('[WebSocket] Connected');
        setConnectionState(WS_STATES.CONNECTED);
        reconnectAttempts.current = 0;
        
        // Re-subscribe to previously subscribed channels
        subscribedChannels.current.forEach(channel => {
          wsRef.current?.send(JSON.stringify({ action: 'subscribe', channel }));
        });
      };
      
      wsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);
          
          // Handle different message types
          switch (data.type) {
            case 'transfer':
              setTransfers(prev => [data.payload, ...prev.slice(0, 49)]);
              break;
            case 'market_stats':
              setMarketStats(data.payload);
              break;
            case 'ping':
              wsRef.current?.send(JSON.stringify({ action: 'pong' }));
              break;
            default:
              break;
          }
        } catch (err) {
          console.warn('[WebSocket] Failed to parse message:', err);
        }
      };
      
      wsRef.current.onclose = (event) => {
        console.log('[WebSocket] Disconnected:', event.code, event.reason);
        setConnectionState(WS_STATES.DISCONNECTED);
        
        // Attempt reconnection with exponential backoff
        if (reconnectAttempts.current < maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000);
          setConnectionState(WS_STATES.RECONNECTING);
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttempts.current += 1;
            connect();
          }, delay);
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error('[WebSocket] Error:', error);
      };
    } catch (err) {
      console.error('[WebSocket] Connection failed:', err);
      setConnectionState(WS_STATES.DISCONNECTED);
    }
  }, [getWsUrl]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close(1000, 'Client disconnect');
      wsRef.current = null;
    }
    setConnectionState(WS_STATES.DISCONNECTED);
  }, []);

  const subscribe = useCallback((channel) => {
    subscribedChannels.current.add(channel);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'subscribe', channel }));
    }
  }, []);

  const unsubscribe = useCallback((channel) => {
    subscribedChannels.current.delete(channel);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'unsubscribe', channel }));
    }
  }, []);

  const sendMessage = useCallback((message) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  // Connect on mount
  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  const value = {
    connectionState,
    isConnected: connectionState === WS_STATES.CONNECTED,
    lastMessage,
    transfers,
    marketStats,
    subscribe,
    unsubscribe,
    sendMessage,
    connect,
    disconnect,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
}

export default WebSocketContext;
