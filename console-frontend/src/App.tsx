import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { DashboardPage } from './pages/DashboardPage';
import { DatasetsPage } from './pages/DatasetsPage';
import { TrainPage } from './pages/TrainPage';
import { EvaluatePage } from './pages/EvaluatePage';
import { PredictPage } from './pages/PredictPage';
import { ApiDocsPage } from './pages/ApiDocsPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { ReportsPage } from './pages/ReportsPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { DatasetProvider } from './lib/DatasetContext';
import { AuthProvider, useAuth } from './lib/AuthContext';
import { LoginPage } from './pages/LoginPage';

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

  return (
    <DatasetProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 ml-56 p-8">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/datasets" element={<DatasetsPage />} />
            <Route path="/train" element={<TrainPage />} />
            <Route path="/evaluate" element={<EvaluatePage />} />
            <Route path="/predict" element={<PredictPage />} />
            <Route path="/api-docs" element={<ApiDocsPage />} />
            <Route path="/onboarding" element={<OnboardingPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
          </Routes>
        </main>
      </div>
    </DatasetProvider>
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
