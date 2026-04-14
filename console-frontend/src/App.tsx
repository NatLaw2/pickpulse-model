import { Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { DataSourcesPage } from './pages/DataSourcesPage';
import { ModelPage } from './pages/ModelPage';
import { PredictPage } from './pages/PredictPage';
import { ApiDocsPage } from './pages/ApiDocsPage';
import { ReportsPage } from './pages/ReportsPage';
import { ExpansionDemoPage } from './pages/ExpansionDemoPage';
import { WelcomePage } from './pages/WelcomePage';
import { WorkflowPage } from './pages/WorkflowPage';
import { DatasetProvider } from './lib/DatasetContext';
import { PredictionProvider } from './lib/PredictionContext';
import { ExecutiveSummaryProvider } from './lib/ExecutiveSummaryContext';
import { ActiveModeProvider, useActiveMode } from './lib/ActiveModeContext';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { LoginPage } from './pages/LoginPage';

// Renders either the WelcomePage (mode=none) or the main app (mode set).
// This is the single routing gate — no page can be accessed without an active mode.
function AppContent() {
  const { mode, loading } = useActiveMode();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
        <div className="text-sm text-[var(--color-text-muted)]">Loading...</div>
      </div>
    );
  }

  // No active mode — show the source-selection welcome page (no sidebar)
  if (mode === 'none') {
    return <WelcomePage />;
  }

  // Mode is set — show the full app with sidebar navigation
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex-1 ml-56 p-8">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/predict" element={<PredictPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/workflow" element={<WorkflowPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/model" element={<ModelPage />} />
          <Route path="/api-docs" element={<ApiDocsPage />} />
          <Route path="/expansion-demo" element={<ExpansionDemoPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function AppShell() {
  const { session, loading } = useAuth();

  console.log('[AppShell] render — loading:', loading, 'session:', !!session);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--color-bg-primary)]">
        <div className="text-sm text-[var(--color-text-muted)]">Loading...</div>
      </div>
    );
  }

  if (!session) {
    return <LoginPage />;
  }

  // ActiveModeProvider is inside the session guard so it only fetches /api/mode
  // when authenticated — prevents spurious 401s on initial load.
  return (
    <ActiveModeProvider>
      <DatasetProvider>
        <PredictionProvider>
          <ExecutiveSummaryProvider>
            <AppContent />
          </ExecutiveSummaryProvider>
        </PredictionProvider>
      </DatasetProvider>
    </ActiveModeProvider>
  );
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
