/**
 * Active Path Context - ETAP C
 * 
 * Global context for managing active path highlighting.
 * 
 * PRINCIPLE:
 * - Click node/edge → highlight connected path
 * - Everything else → dimmed
 * - ESC / click empty → reset
 * - NO layout recalculation
 * - Pure visual layer
 */

import { createContext, useContext, useState, useCallback } from 'react';

const ActivePathContext = createContext(null);

/**
 * Active Path Provider
 * Wrap at App level for global access
 */
export function ActivePathProvider({ children }) {
  // activePath = { nodes: Set<string>, edges: Set<string> } | null
  const [activePath, setActivePath] = useState(null);
  
  const clearPath = useCallback(() => {
    setActivePath(null);
  }, []);
  
  const isNodeActive = useCallback((nodeId) => {
    if (!activePath) return true; // No active path = all active
    return activePath.nodes.has(nodeId);
  }, [activePath]);
  
  const isEdgeActive = useCallback((edgeId) => {
    if (!activePath) return true;
    return activePath.edges.has(edgeId);
  }, [activePath]);
  
  return (
    <ActivePathContext.Provider
      value={{
        activePath,
        setActivePath,
        clearPath,
        isActive: !!activePath,
        isNodeActive,
        isEdgeActive,
      }}
    >
      {children}
    </ActivePathContext.Provider>
  );
}

/**
 * Hook to access active path context
 */
export function useActivePath() {
  const context = useContext(ActivePathContext);
  if (!context) {
    // Return dummy for components outside provider
    return {
      activePath: null,
      setActivePath: () => {},
      clearPath: () => {},
      isActive: false,
      isNodeActive: () => true,
      isEdgeActive: () => true,
    };
  }
  return context;
}

export default ActivePathContext;
