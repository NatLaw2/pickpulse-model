import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import { api, type DatasetInfo } from './api';

interface DatasetState {
  dataset: DatasetInfo | null;
  loading: boolean;
  refresh: () => void;
}

const DatasetContext = createContext<DatasetState>({
  dataset: null,
  loading: true,
  refresh: () => {},
});

export function DatasetProvider({ children }: { children: ReactNode }) {
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    setLoading(true);
    api.currentDataset()
      .then(setDataset)
      .catch(() => setDataset(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <DatasetContext.Provider value={{ dataset, loading, refresh }}>
      {children}
    </DatasetContext.Provider>
  );
}

export function useDataset() {
  return useContext(DatasetContext);
}
