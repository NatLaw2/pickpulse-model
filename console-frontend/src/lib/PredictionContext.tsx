import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { api, type PredictResponse } from './api';
import { useDataset } from './DatasetContext';

const STORAGE_KEY = 'pickpulse_predictions';

interface PredictionState {
  predictions: PredictResponse | null;
  loading: boolean;
  setPredictions: (data: PredictResponse) => void;
  clearPredictions: () => void;
  loadCached: () => Promise<void>;
}

const PredictionContext = createContext<PredictionState>({
  predictions: null,
  loading: false,
  setPredictions: () => {},
  clearPredictions: () => {},
  loadCached: async () => {},
});

export function PredictionProvider({ children }: { children: ReactNode }) {
  const [predictions, setPredictionsState] = useState<PredictResponse | null>(null);
  // loading is true while loadCached() is fetching from the backend
  const [loading, setLoading] = useState(false);
  const { dataset } = useDataset();
  const prevDatasetRef = useRef(dataset?.loaded_at);

  // Invalidate predictions when dataset changes
  useEffect(() => {
    if (prevDatasetRef.current && prevDatasetRef.current !== dataset?.loaded_at) {
      setPredictionsState(null);
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    }
    prevDatasetRef.current = dataset?.loaded_at;
  }, [dataset?.loaded_at]);

  const setPredictions = useCallback((data: PredictResponse) => {
    setPredictionsState(data);
    try {
      // Store alongside the current dataset token so cross-session restores
      // can be validated against the active dataset.
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        data,
        dataset_loaded_at: dataset?.loaded_at ?? null,
      }));
    } catch { /* quota exceeded — not critical */ }
  }, [dataset?.loaded_at]);

  const clearPredictions = useCallback(() => {
    setPredictionsState(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, []);

  const loadCached = useCallback(async () => {
    // Already loaded in context — nothing to do
    if (predictions) return;

    setLoading(true);
    try {
      // Always try the backend first — it holds the authoritative source context
      // (dataset vs CRM provider).  This is what prevents stale sessionStorage from
      // showing CSV data when a CRM integration is active, and vice-versa.
      try {
        const cached = await api.cachedPredictions();
        if (cached?.predictions?.length) {
          setPredictionsState(cached);
          return;
        }
      } catch { /* no cached predictions on backend — fall through to sessionStorage */ }

      // sessionStorage fallback: only for CSV/dataset mode predictions (never CRM)
      try {
        const stored = sessionStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored);
          // Support both new keyed format { data, dataset_loaded_at } and legacy bare PredictResponse
          const cachedData: PredictResponse = parsed.data ?? parsed;
          const cachedDatasetAt: string | null = parsed.dataset_loaded_at ?? null;
          // Never restore CRM predictions from sessionStorage — backend is authoritative for CRM context
          if (cachedData.crm_mode) {
            try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
          } else if (cachedDatasetAt !== null && dataset?.loaded_at !== null && cachedDatasetAt !== dataset?.loaded_at) {
            // Dataset token mismatch — stale from prior dataset
            try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
          } else if (cachedData.predictions?.length && dataset?.loaded_at) {
            // Only restore if there is an active dataset to match against
            setPredictionsState(cachedData);
            return;
          }
        }
      } catch { /* corrupt data — fall through */ }
    } finally {
      setLoading(false);
    }
  }, [predictions, dataset?.loaded_at]);

  return (
    <PredictionContext.Provider value={{ predictions, loading, setPredictions, clearPredictions, loadCached }}>
      {children}
    </PredictionContext.Provider>
  );

}

export function usePredictions() {
  return useContext(PredictionContext);
}
