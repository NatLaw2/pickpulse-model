import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import { api } from './api';

// The four possible states — never the generic string "crm"
export type ActiveMode = 'salesforce' | 'hubspot' | 'csv' | 'none';

interface ActiveModeState {
  mode: ActiveMode;
  loading: boolean;
  /** Set mode on backend and update local state. */
  setMode: (mode: ActiveMode) => Promise<void>;
}

const ActiveModeContext = createContext<ActiveModeState>({
  mode: 'none',
  loading: true,
  setMode: async () => {},
});

export function ActiveModeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ActiveMode>('none');
  const [loading, setLoading] = useState(true);

  // On mount, fetch the authoritative mode from the backend.
  // This is the ONLY source of truth — sessionStorage / localStorage are not consulted.
  useEffect(() => {
    api.getMode()
      .then((data) => {
        const m = data.mode as ActiveMode;
        setModeState(['salesforce', 'hubspot', 'csv'].includes(m) ? m : 'none');
      })
      .catch(() => setModeState('none'))
      .finally(() => setLoading(false));
  }, []);

  const setMode = useCallback(async (newMode: ActiveMode) => {
    // Persist to backend first — if the call fails we don't update local state.
    await api.setMode(newMode);
    setModeState(newMode);
  }, []);

  return (
    <ActiveModeContext.Provider value={{ mode, loading, setMode }}>
      {children}
    </ActiveModeContext.Provider>
  );
}

export function useActiveMode() {
  return useContext(ActiveModeContext);
}
