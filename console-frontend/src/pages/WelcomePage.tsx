import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Cloud, Upload, Zap } from 'lucide-react';
import { useActiveMode, type ActiveMode } from '../lib/ActiveModeContext';
import { usePredictions } from '../lib/PredictionContext';

const SOURCE_CARDS: {
  mode: Exclude<ActiveMode, 'none'>;
  label: string;
  description: string;
  icon: React.ElementType;
  href: string;
}[] = [
  {
    mode: 'salesforce',
    label: 'Salesforce',
    description: 'Sync accounts and engagement signals directly from Salesforce CRM.',
    icon: Cloud,
    href: '/data-sources?tab=integrations',
  },
  {
    mode: 'hubspot',
    label: 'HubSpot',
    description: 'Sync contacts and deal activity from HubSpot.',
    icon: Zap,
    href: '/data-sources?tab=integrations',
  },
  {
    mode: 'csv',
    label: 'Upload CSV',
    description: 'Upload your own customer data file to generate churn predictions.',
    icon: Upload,
    href: '/data-sources',
  },
];

export function WelcomePage() {
  const navigate = useNavigate();
  const { setMode } = useActiveMode();
  const { clearPredictions } = usePredictions();
  const [selecting, setSelecting] = useState<ActiveMode | null>(null);

  const handleSelect = async (mode: Exclude<ActiveMode, 'none'>, href: string) => {
    if (selecting) return;
    setSelecting(mode);
    try {
      clearPredictions();
      await setMode(mode);
      navigate(href);
    } catch {
      // If setMode fails, remain on welcome page
      setSelecting(null);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-[var(--color-bg-primary)] px-6">
      <div className="max-w-2xl w-full">
        <div className="text-center mb-10">
          <h1 className="text-2xl font-bold mb-2">Connect Your Data</h1>
          <p className="text-sm text-[var(--color-text-secondary)]">
            Choose a source to begin. All predictions, scores, and reports are scoped to this source.
            Use Reset at any time to switch.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {SOURCE_CARDS.map(({ mode, label, description, icon: Icon, href }) => (
            <button
              key={mode}
              onClick={() => handleSelect(mode, href)}
              disabled={selecting !== null}
              className="text-left bg-white border border-[var(--color-border)] rounded-2xl p-5 hover:border-[var(--color-accent)] hover:shadow-[0_0_0_1px_var(--color-accent)] transition-all disabled:opacity-60 shadow-[0_1px_3px_rgba(0,0,0,0.08)]"
            >
              <Icon size={22} className="text-[var(--color-accent)] mb-3" />
              <h3 className="font-semibold text-sm mb-1">
                {selecting === mode ? 'Setting up…' : label}
              </h3>
              <p className="text-xs text-[var(--color-text-secondary)]">{description}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
