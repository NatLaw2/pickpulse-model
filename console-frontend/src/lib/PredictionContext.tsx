import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { api, type PredictResponse } from './api';
import { useDataset } from './DatasetContext';

// sessionStorage is intentionally NOT used in this context.
// The backend is the single source of truth for predictions.
// Any mode that is not explicitly set returns 404 from the backend,
// which keeps the UI in an empty/unpopulated state.

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

  // Invalidate predictions when the CSV dataset changes (new upload replaces old).
  // This does not affect CRM mode — dataset is always null there.
  useEffect(() => {
    if (prevDatasetRef.current && prevDatasetRef.current !== dataset?.loaded_at) {
      setPredictionsState(null);
    }
    prevDatasetRef.current = dataset?.loaded_at;
  }, [dataset?.loaded_at]);

  const setPredictions = useCallback((data: PredictResponse) => {
    setPredictionsState(data);
  }, []);

  const clearPredictions = useCallback(() => {
    setPredictionsState(null);
  }, []);

  const loadCached = useCallback(async () => {
    if (predictions) return;

    setLoading(true);
    try {
      // Backend is the single source of truth.
      // Returns 404 when:
      //   - mode is none (no source selected yet)
      //   - no predictions have been generated for the current mode
      // In both cases predictions remain null — no pre-population occurs.
      const cached = await api.cachedPredictions();
      if (cached?.predictions?.length) {
        setPredictionsState(cached);
      }
    } catch {
      // 404 or network error — nothing to restore, stay empty
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
