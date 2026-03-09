import { useState, useCallback, useEffect } from 'react';
import { api, type ExecutiveSummaryResponse } from './api';

const STORAGE_KEY = 'pickpulse_executive_summary';

/**
 * Shared hook for executive summary state — persists across page navigation
 * via sessionStorage. Both DashboardPage and PredictPage use this.
 */
export function useExecutiveSummary() {
  const [summaryData, setSummaryDataState] = useState<ExecutiveSummaryResponse | null>(() => {
    // Initialize from sessionStorage
    try {
      const stored = sessionStorage.getItem(STORAGE_KEY);
      if (stored) return JSON.parse(stored) as ExecutiveSummaryResponse;
    } catch { /* ignore */ }
    return null;
  });
  const [showModal, setShowModal] = useState(false);
  const [loading, setLoading] = useState(false);

  const setSummaryData = useCallback((data: ExecutiveSummaryResponse | null) => {
    setSummaryDataState(data);
    try {
      if (data) {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
      } else {
        sessionStorage.removeItem(STORAGE_KEY);
      }
    } catch { /* quota exceeded */ }
  }, []);

  const clearSummary = useCallback(() => {
    setSummaryDataState(null);
    try { sessionStorage.removeItem(STORAGE_KEY); } catch { /* ignore */ }
  }, []);

  /** Build a mailto: URL from the summary data. */
  const buildMailtoUrl = useCallback(() => {
    if (!summaryData) return '';

    const subject = encodeURIComponent(summaryData.subject);

    // Extract plain-text version from HTML
    const doc = new DOMParser().parseFromString(summaryData.html_body, 'text/html');
    const plainText = doc.body.innerText
      .replace(/\n{3,}/g, '\n\n')  // collapse excessive newlines
      .trim();

    const body = encodeURIComponent(plainText);
    const to = summaryData.recipients.length > 0
      ? summaryData.recipients.join(',')
      : '';

    return `mailto:${to}?subject=${subject}&body=${body}`;
  }, [summaryData]);

  return {
    summaryData,
    setSummaryData,
    clearSummary,
    showModal,
    setShowModal,
    loading,
    setLoading,
    buildMailtoUrl,
  };
}
