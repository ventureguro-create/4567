import { useEffect, useState } from 'react';
import { apiGet } from '../api/client';

export function useDashboard(page = 1, limit = 20) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let active = true;

    async function load() {
      try {
        setLoading(true);
        const result = await apiGet(
          `/api/frontend/dashboard?page=${page}&limit=${limit}`
        );
        if (active) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err.message);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    load();
    const interval = setInterval(load, 60000); // Poll every 60s

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [page, limit]);

  return { data, loading, error };
}
