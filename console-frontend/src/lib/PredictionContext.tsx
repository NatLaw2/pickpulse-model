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
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch { /* quota exceeded — not critical */ }
  }, []);

  const clearPredictions = useCallback(() => {
    setPredictionsState(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, []);

  const loadCached = useCallback(async () => {
    // Already loaded in context — nothing to do
    if (predictions) return;

    // Try sessionStorage first
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored) as PredictResponse;
        if (parsed.predictions?.length) {
          setPredictionsState(parsed);
          return;
        }
      }
    } catch { /* corrupt data — fall through */ }

    // Last resort: backend cached endpoint
    setLoading(true);
    try {
      const res = await api.cachedPredictions();
      setPredictionsState(res);
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(res));
      } catch { /* ignore */ }
    } catch {
      // 404 = no cached predictions, not an error
    } finally {
      setLoading(false);
    }
  }, [predictions]);

  return (
    <PredictionContext.Provider value={{ predictions, loading, setPredictions, clearPredictions, loadCached }}>
      {children}
    </PredictionContext.Provider>
  );
}

export function usePredictions() {
  return useContext(PredictionContext);
}
