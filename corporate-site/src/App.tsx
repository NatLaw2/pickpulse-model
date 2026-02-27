import { Routes, Route, useLocation } from 'react-router-dom';
import { Navbar } from './components/Navbar';
import { Footer } from './components/Footer';
import { HomePage } from './pages/HomePage';
import { ModulesPage } from './pages/ModulesPage';
import { ChurnPage } from './pages/ChurnPage';
import { DemoPage } from './pages/DemoPage';
import { ContactPage } from './pages/ContactPage';
import { AboutPage } from './pages/AboutPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { LeaveBehind } from './pages/LeaveBehind';

/** Routes that render without the site chrome (Navbar/Footer). */
const STANDALONE = ['/leave-behind'];

function App() {
  const { pathname } = useLocation();
  const isStandalone = STANDALONE.includes(pathname);

  return (
    <div className="flex flex-col min-h-screen">
      {!isStandalone && <Navbar />}
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/modules" element={<ModulesPage />} />
          <Route path="/modules/churn" element={<ChurnPage />} />
          <Route path="/demo" element={<DemoPage />} />
          <Route path="/contact" element={<ContactPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/onboarding" element={<OnboardingPage />} />
          <Route path="/leave-behind" element={<LeaveBehind />} />
        </Routes>
      </main>
      {!isStandalone && <Footer />}
    </div>
  );
}

export default App;
