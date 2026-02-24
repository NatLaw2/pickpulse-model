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
import { DatasetProvider } from './lib/DatasetContext';

function App() {
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
          </Routes>
        </main>
      </div>
    </DatasetProvider>
  );
}

export default App;
