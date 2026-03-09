import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import { type ExecutiveSummaryResponse } from './api';
import { useDataset } from './DatasetContext';
import { usePredictions } from './PredictionContext';

const STORAGE_KEY = 'pickpulse_executive_summary';

interface ExecutiveSummaryState {
  summaryData: ExecutiveSummaryResponse | null;
  setSummaryData: (data: ExecutiveSummaryResponse) => void;
  clearSummary: () => void;
  showModal: boolean;
  setShowModal: (show: boolean) => void;
  buildMailtoUrl: () => string;
  getPlainText: () => string;
}

const ExecutiveSummaryContext = createContext<ExecutiveSummaryState>({
  summaryData: null,
  setSummaryData: () => {},
  clearSummary: () => {},
  showModal: false,
  setShowModal: () => {},
  buildMailtoUrl: () => '',
  getPlainText: () => '',
});

export function ExecutiveSummaryProvider({ children }: { children: ReactNode }) {
  const [summaryData, setSummaryDataState] = useState<ExecutiveSummaryResponse | null>(() => {
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) return JSON.parse(stored) as ExecutiveSummaryResponse;
    } catch { /* ignore */ }
    return null;
  });
  const [showModal, setShowModal] = useState(false);

  const { dataset } = useDataset();
  const { predictions } = usePredictions();
  const prevDatasetRef = useRef(dataset?.loaded_at);
  const prevPredictionsRef = useRef(predictions);

  // Invalidate when dataset changes
  useEffect(() => {
    if (prevDatasetRef.current && prevDatasetRef.current !== dataset?.loaded_at) {
      setSummaryDataState(null);
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    }
    prevDatasetRef.current = dataset?.loaded_at;
  }, [dataset?.loaded_at]);

  // Invalidate when predictions are regenerated (new prediction result replaces old)
  useEffect(() => {
    const prev = prevPredictionsRef.current;
    const curr = predictions;
    // If predictions changed from one set to a different set, clear the brief
    // so it gets regenerated with fresh data
    if (prev && curr && prev !== curr && prev.predictions !== curr.predictions) {
      setSummaryDataState(null);
      try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
    }
    prevPredictionsRef.current = curr;
  }, [predictions]);

  const setSummaryData = useCallback((data: ExecutiveSummaryResponse) => {
    setSummaryDataState(data);
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch { /* quota exceeded */ }
  }, []);

  const clearSummary = useCallback(() => {
    setSummaryDataState(null);
    setShowModal(false);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, []);

  const getPlainText = useCallback(() => {
    if (!summaryData) return '';
    const doc = new DOMParser().parseFromString(summaryData.html_body, 'text/html');
    return doc.body.innerText.replace(/\n{3,}/g, '\n\n').trim();
  }, [summaryData]);

  const buildMailtoUrl = useCallback(() => {
    if (!summaryData) return '';
    const subject = encodeURIComponent(summaryData.subject);
    const body = encodeURIComponent(getPlainText());
    const to = summaryData.recipients.length > 0
      ? summaryData.recipients.join(',')
      : '';
    return `mailto:${to}?subject=${subject}&body=${body}`;
  }, [summaryData, getPlainText]);

  return (
    <ExecutiveSummaryContext.Provider value={{
      summaryData,
      setSummaryData,
      clearSummary,
      showModal,
      setShowModal,
      buildMailtoUrl,
      getPlainText,
    }}>
      {children}
    </ExecutiveSummaryContext.Provider>
  );
}

export function useExecutiveSummary() {
  return useContext(ExecutiveSummaryContext);
}
