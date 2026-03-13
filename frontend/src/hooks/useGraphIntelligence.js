/**
 * useGraphIntelligence Hook (P1.8 + STABILIZATION + ETAP B1)
 * 
 * Main hook for fetching and managing graph intelligence data.
 * Combines API calls with store management.
 * 
 * ETAP B1: Network-scoped queries
 * - Uses global network from useNetworkStore
 * - Re-fetches when network changes
 * 
 * STABILIZATION:
 * - useShallow for selector memoization
 * - Stable refs to prevent re-render loops
 * - Request deduplication
 */

import { useCallback, useEffect, useRef, useMemo } from 'react';
import { shallow } from 'zustand/shallow';
const useShallow = shallow;
import useGraphIntelligenceStore from '../state/graphIntelligence.store';
import useNetworkStore from '../state/network.store';
import { fetchGraphByAddress, fetchGraphByRoute } from '../api/graphIntelligence.api';

/**
 * Hook for graph intelligence data
 * 
 * ETAP B1: Uses global network from useNetworkStore
 * 
 * STABILIZATION: Uses useShallow to batch state subscriptions
 * and prevent re-renders from unrelated state changes.
 * 
 * P2.2: Now supports calibrated mode via options.mode
 * - Default is 'calibrated' for full P2.2 features (corridors, weights)
 * - Set mode: 'raw' for legacy behavior
 * 
 * @param {Object} params
 * @param {string} params.address - Wallet address (optional)
 * @param {string} params.routeId - Route ID (optional)
 * @param {Object} params.options - Query options
 * @param {string} params.options.mode - 'raw' | 'calibrated' (default: 'calibrated')
 * @param {boolean} params.autoFetch - Whether to fetch on mount
 */
export function useGraphIntelligence({
  address,
  routeId,
  options = {},
  autoFetch = true,
} = {}) {
  // ETAP B1: Get current network from global store
  const network = useNetworkStore(state => state.network);
  
  // P2.2: Default to calibrated mode + ETAP B1 network
  const effectiveOptions = useMemo(() => ({
    mode: 'calibrated', // P2.2 default
    network,            // ETAP B1: Include network
    ...options,
  }), [network, options]);
  
  // STABILIZATION: Use useShallow to batch state subscriptions
  // This prevents re-renders when unrelated state changes
  const { 
    graph, 
    loading, 
    error, 
    focusMode, 
    selectedEdgeId 
  } = useGraphIntelligenceStore(
    useShallow(state => ({
      graph: state.graph,
      loading: state.loading,
      error: state.error,
      focusMode: state.focusMode,
      selectedEdgeId: state.selectedEdgeId,
    }))
  );
  
  // STABILIZATION: Use useShallow for actions to get stable refs
  const actions = useGraphIntelligenceStore(
    useShallow(state => ({
      setGraph: state.setGraph,
      setLoading: state.setLoading,
      setError: state.setError,
      clearGraph: state.clearGraph,
      setFocusMode: state.setFocusMode,
      toggleFocusMode: state.toggleFocusMode,
      selectEdge: state.selectEdge,
      clearEdgeSelection: state.clearEdgeSelection,
    }))
  );
  
  // STABILIZATION: Track in-flight requests to prevent duplicates
  const fetchedRef = useRef(false);
  const lastAddressRef = useRef(null);
  const lastRouteIdRef = useRef(null);
  const lastNetworkRef = useRef(null); // ETAP B1: Track network changes
  const abortControllerRef = useRef(null);
  const isMountedRef = useRef(true);
  
  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    };
  }, []);
  
  // Fetch graph by address
  const fetchByAddress = useCallback(async (addr, opts = {}) => {
    const targetAddress = addr || address;
    if (!targetAddress) return;
    
    // STABILIZATION: Abort previous request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    actions.setLoading(true);
    actions.setError(null);
    
    try {
      // ETAP B1 + P2.2: Use effectiveOptions (includes network + mode)
      const data = await fetchGraphByAddress(targetAddress, { ...effectiveOptions, ...opts });
      
      // STABILIZATION: Only update if still mounted
      if (isMountedRef.current) {
        actions.setGraph(data);
      }
    } catch (err) {
      if (err.name !== 'AbortError' && isMountedRef.current) {
        actions.setError(err.message);
      }
    } finally {
      if (isMountedRef.current) {
        actions.setLoading(false);
      }
    }
  }, [address, effectiveOptions, actions]);
  
  // Fetch graph by route
  const fetchByRoute = useCallback(async (id, opts = {}) => {
    const targetRouteId = id || routeId;
    if (!targetRouteId) return;
    
    // STABILIZATION: Abort previous request
    abortControllerRef.current?.abort();
    abortControllerRef.current = new AbortController();
    
    actions.setLoading(true);
    actions.setError(null);
    
    try {
      // ETAP B1 + P2.2: Use effectiveOptions (includes network + mode)
      const data = await fetchGraphByRoute(targetRouteId, { ...effectiveOptions, ...opts });
      
      // STABILIZATION: Only update if still mounted
      if (isMountedRef.current) {
        actions.setGraph(data);
      }
    } catch (err) {
      if (err.name !== 'AbortError' && isMountedRef.current) {
        actions.setError(err.message);
      }
    } finally {
      if (isMountedRef.current) {
        actions.setLoading(false);
      }
    }
  }, [routeId, effectiveOptions, actions]);
  
  // ETAP B1: Re-fetch when network changes
  useEffect(() => {
    if (!autoFetch) return;
    
    const networkChanged = network !== lastNetworkRef.current;
    
    // Check if address or routeId changed
    const addressChanged = address && address !== lastAddressRef.current;
    const routeIdChanged = routeId && routeId !== lastRouteIdRef.current;
    
    // ETAP B1: Re-fetch on network change
    if (networkChanged && lastNetworkRef.current !== null) {
      lastNetworkRef.current = network;
      // Clear current graph and re-fetch
      actions.clearGraph();
      if (address) {
        fetchByAddress(address);
      } else if (routeId) {
        fetchByRoute(routeId);
      }
      return;
    }
    
    lastNetworkRef.current = network;
    
    if (addressChanged) {
      lastAddressRef.current = address;
      lastRouteIdRef.current = null;
      fetchByAddress(address);
    } else if (routeIdChanged) {
      lastRouteIdRef.current = routeId;
      lastAddressRef.current = null;
      fetchByRoute(routeId);
    } else if (!fetchedRef.current && (address || routeId)) {
      fetchedRef.current = true;
      if (address) {
        lastAddressRef.current = address;
        fetchByAddress(address);
      } else if (routeId) {
        lastRouteIdRef.current = routeId;
        fetchByRoute(routeId);
      }
    }
  }, [address, routeId, network, autoFetch, fetchByAddress, fetchByRoute, actions]);
  
  // STABILIZATION: Memoized derived values
  // These only recompute when graph changes
  const highlightedPath = useMemo(() => {
    return graph?.highlightedPath || [];
  }, [graph?.highlightedPath]);
  
  const highlightedNodeIds = useMemo(() => {
    if (!graph?.highlightedPath || !graph?.edges) return new Set();
    
    const edgeIds = new Set(graph.highlightedPath.map(step => step.edgeId));
    const nodeIds = new Set();
    
    for (const edge of graph.edges) {
      if (edgeIds.has(edge.id)) {
        nodeIds.add(edge.fromNodeId);
        nodeIds.add(edge.toNodeId);
      }
    }
    
    return nodeIds;
  }, [graph?.highlightedPath, graph?.edges]);
  
  const highlightedEdges = useMemo(() => {
    if (!graph?.highlightedPath || !graph?.edges) return [];
    const edgeIds = new Set(graph.highlightedPath.map(step => step.edgeId));
    return graph.edges.filter(edge => edgeIds.has(edge.id));
  }, [graph?.highlightedPath, graph?.edges]);
  
  // STABILIZATION: Simple derived values (no memoization needed)
  const riskSummary = graph?.riskSummary || null;
  const explain = graph?.explain || null;
  const hasGraph = graph !== null && graph?.nodes?.length > 0;
  
  // P2.2: Calibration-specific data
  const corridors = graph?.corridors || [];
  const calibrationMeta = graph?.calibrationMeta || null;
  const isCalibrated = calibrationMeta !== null;
  
  const selectedEdge = useMemo(() => {
    if (!graph || !selectedEdgeId) return null;
    const edge = graph.edges?.find(e => e.id === selectedEdgeId);
    const step = highlightedPath.find(s => s.edgeId === selectedEdgeId);
    return edge ? { edge, step, isHighlighted: !!step } : null;
  }, [graph, selectedEdgeId, highlightedPath]);
  
  const metadata = useMemo(() => {
    if (!graph) return null;
    return {
      snapshotId: graph.snapshotId,
      kind: graph.kind,
      address: graph.address,
      routeId: graph.routeId,
      generatedAt: graph.generatedAt,
      expiresAt: graph.expiresAt,
      buildTimeMs: graph.buildTimeMs,
      nodesCount: graph.nodes?.length || 0,
      edgesCount: graph.edges?.length || 0,
      highlightedCount: graph.highlightedPath?.length || 0,
      truncated: graph.truncated || false,
      // P2.2: Calibration metadata
      isCalibrated,
      corridorCount: corridors.length,
      calibrationVersion: calibrationMeta?.version || null,
    };
  }, [graph, isCalibrated, corridors.length, calibrationMeta?.version]);
  
  return {
    // State
    graph,
    loading,
    error,
    focusMode,
    selectedEdgeId,
    
    // Actions (spread from actions object for stable refs)
    fetchByAddress,
    fetchByRoute,
    clearGraph: actions.clearGraph,
    setFocusMode: actions.setFocusMode,
    toggleFocusMode: actions.toggleFocusMode,
    selectEdge: actions.selectEdge,
    clearEdgeSelection: actions.clearEdgeSelection,
    
    // Derived (memoized)
    highlightedPath,
    highlightedNodeIds,
    highlightedEdges,
    riskSummary,
    explain,
    selectedEdge,
    metadata,
    hasGraph,
    
    // P2.2: Calibration data
    corridors,
    calibrationMeta,
    isCalibrated,
  };
}

export default useGraphIntelligence;
