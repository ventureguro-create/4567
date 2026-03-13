/**
 * useChainFilter Hook (P2.3.3 BLOCK 2)
 * 
 * Manages multi-chain filter state with URL persistence
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { getAllChains } from '../utils/chainMeta';

/**
 * Parse chains from URL params
 */
function parseChainsFromUrl(searchParams) {
  const chainsParam = searchParams.get('chains');
  if (!chainsParam) return [];
  
  const chains = chainsParam.split(',').map(c => c.toUpperCase()).filter(Boolean);
  const validChains = getAllChains();
  
  // Only return valid chains
  return chains.filter(c => validChains.includes(c));
}

/**
 * Hook for managing chain filter state
 */
export function useChainFilter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedChains, setSelectedChains] = useState(() => {
    return parseChainsFromUrl(searchParams);
  });
  
  // Sync with URL on mount and when URL changes
  useEffect(() => {
    const urlChains = parseChainsFromUrl(searchParams);
    setSelectedChains(urlChains);
  }, [searchParams]);
  
  // Update URL when selection changes
  const updateUrl = useCallback((chains) => {
    const newParams = new URLSearchParams(searchParams);
    
    if (chains.length === 0) {
      newParams.delete('chains');
    } else {
      newParams.set('chains', chains.map(c => c.toLowerCase()).join(','));
    }
    
    setSearchParams(newParams, { replace: true });
  }, [searchParams, setSearchParams]);
  
  // Toggle a single chain
  const toggleChain = useCallback((chain) => {
    const chainUpper = chain.toUpperCase();
    setSelectedChains(prev => {
      const newSelection = prev.includes(chainUpper)
        ? prev.filter(c => c !== chainUpper)
        : [...prev, chainUpper];
      
      updateUrl(newSelection);
      return newSelection;
    });
  }, [updateUrl]);
  
  // Clear filter (show all chains)
  const clearFilter = useCallback(() => {
    setSelectedChains([]);
    updateUrl([]);
  }, [updateUrl]);
  
  // Select all chains
  const selectAll = useCallback(() => {
    const allChains = getAllChains();
    setSelectedChains(allChains);
    updateUrl(allChains);
  }, [updateUrl]);
  
  // Check if a specific chain is selected
  const isChainSelected = useCallback((chain) => {
    if (selectedChains.length === 0) return true; // No filter = all selected
    return selectedChains.includes(chain.toUpperCase());
  }, [selectedChains]);
  
  // Check if filter is active
  const isFilterActive = useMemo(() => {
    return selectedChains.length > 0 && selectedChains.length < getAllChains().length;
  }, [selectedChains]);
  
  return {
    selectedChains,
    toggleChain,
    clearFilter,
    selectAll,
    isChainSelected,
    isFilterActive
  };
}

/**
 * Filter events by selected chains
 * 
 * For bridge events, show if either chainFrom OR chainTo is selected
 */
export function filterEventsByChains(events, selectedChains) {
  if (!selectedChains || selectedChains.length === 0) {
    return events; // No filter = show all
  }
  
  return events.filter(event => {
    // Bridge events: check both chainFrom and chainTo
    if (event.chainFrom && event.chainTo) {
      return (
        selectedChains.includes(event.chainFrom.toUpperCase()) ||
        selectedChains.includes(event.chainTo.toUpperCase())
      );
    }
    
    // Regular events: check chain
    if (event.chain) {
      return selectedChains.includes(event.chain.toUpperCase());
    }
    
    // No chain info = show it
    return true;
  });
}
