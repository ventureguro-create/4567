/**
 * useActorClusters Hook (P2.2)
 * 
 * Fetch and manage actor clustering data
 */
import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_URL = process.env.REACT_APP_BACKEND_URL || '';

/**
 * Get all clusters
 */
export function useClusters(limit = 100) {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const fetchClusters = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/api/actors/clusters`, {
        params: { limit },
      });
      
      if (response.data.ok) {
        setClusters(response.data.data.clusters || []);
      }
    } catch (err) {
      console.error('Error fetching clusters:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [limit]);
  
  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);
  
  return { clusters, loading, error, refetch: fetchClusters };
}

/**
 * Get cluster for specific wallet
 */
export function useWalletCluster(address, chain = 'ETH') {
  const [cluster, setCluster] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const fetchCluster = useCallback(async () => {
    if (!address) return;
    
    try {
      setLoading(true);
      const response = await axios.get(
        `${API_URL}/api/actors/wallet/${address}/cluster`,
        { params: { chain } }
      );
      
      if (response.data.ok && response.data.data) {
        setCluster(response.data.data);
      } else {
        setCluster(null);
      }
    } catch (err) {
      console.error('Error fetching wallet cluster:', err);
      setError(err.message);
      setCluster(null);
    } finally {
      setLoading(false);
    }
  }, [address, chain]);
  
  useEffect(() => {
    fetchCluster();
  }, [fetchCluster]);
  
  return { cluster, loading, error, refetch: fetchCluster };
}

/**
 * Get cluster by ID
 */
export function useCluster(clusterId) {
  const [cluster, setCluster] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const fetchCluster = useCallback(async () => {
    if (!clusterId) return;
    
    try {
      setLoading(true);
      const response = await axios.get(
        `${API_URL}/api/actors/clusters/${clusterId}`
      );
      
      if (response.data.ok) {
        setCluster(response.data.data);
      }
    } catch (err) {
      console.error('Error fetching cluster:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [clusterId]);
  
  useEffect(() => {
    fetchCluster();
  }, [fetchCluster]);
  
  return { cluster, loading, error, refetch: fetchCluster };
}

/**
 * Get clustering summary stats
 */
export function useClusteringSummary() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const fetchSummary = useCallback(async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/api/actors/clusters/summary`);
      
      if (response.data.ok) {
        setSummary(response.data.data);
      }
    } catch (err) {
      console.error('Error fetching clustering summary:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);
  
  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);
  
  return { summary, loading, error, refetch: fetchSummary };
}

export default {
  useClusters,
  useWalletCluster,
  useCluster,
  useClusteringSummary,
};
