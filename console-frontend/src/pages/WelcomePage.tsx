import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Cloud, Upload } from 'lucide-react';
import { useActiveMode, type ActiveMode } from '../lib/ActiveModeContext';
import { usePredictions } from '../lib/PredictionContext';

// Inline HubSpot asterisk icon — no external assets
function HubSpotIcon() {
  return (
    <div
      className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
      style={{ background: '#FF7A59' }}
    >
      <svg width="26" height="26" viewBox="0 0 20 20" fill="none">
        <circle cx="10" cy="10" r="3.5" fill="white" />
        <circle cx="10" cy="3" r="1.5" fill="white" />
        <circle cx="10" cy="17" r="1.5" fill="white" />
        <circle cx="3" cy="10" r="1.5" fill="white" />
        <circle cx="17" cy="10" r="1.5" fill="white" />
        <circle cx="5.05" cy="5.05" r="1.5" fill="white" />
        <circle cx="14.95" cy="14.95" r="1.5" fill="white" />
        <circle cx="14.95" cy="5.05" r="1.5" fill="white" />
        <circle cx="5.05" cy="14.95" r="1.5" fill="white" />
      </svg>
    </div>
  );
}

// Salesforce cloud icon — Salesforce blue
function SalesforceIcon() {
  return (
    <div
      className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
      style={{ background: '#00A1E0' }}
    >
      <Cloud size={26} color="white" strokeWidth={2.2} />
    </div>
  );
}

// CSV upload icon — product accent color
function CsvIcon() {
  return (
    <div className="w-12 h-12 rounded-2xl bg-[var(--color-accent)]/12 flex items-center justify-center mx-auto mb-4">
      <Upload size={24} className="text-[var(--color-accent)]" />
    </div>
  );
}

const SOURCE_CARDS: {
  mode: Exclude<ActiveMode, 'none'>;
  label: string;
  description: string;
  IconComponent: () => JSX.Element;
  accent: string;
  borderHover: string;
  ringHover: string;
}[] = [
  {
    mode: 'salesforce',
    label: 'Salesforce',
    description: 'Sync accounts and engagement signals directly from your Salesforce CRM.',
    IconComponent: SalesforceIcon,
    accent: 'text-[#00A1E0]',
    borderHover: 'hover:border-[#00A1E0]/50',
    ringHover: 'hover:shadow-[0_0_0_1px_rgba(0,161,224,0.35)]',
  },
  {
    mode: 'hubspot',
    label: 'HubSpot',
    description: 'Pull contacts, deals, and activity directly from HubSpot.',
    IconComponent: HubSpotIcon,
    accent: 'text-[#FF7A59]',
    borderHover: 'hover:border-[#FF7A59]/50',
    ringHover: 'hover:shadow-[0_0_0_1px_rgba(255,122,89,0.35)]',
  },
  {
    mode: 'csv',
    label: 'Upload CSV',
    description: 'Upload your own customer data file to generate churn predictions.',
    IconComponent: CsvIcon,
    accent: 'text-[var(--color-accent)]',
    borderHover: 'hover:border-[var(--color-accent)]',
    ringHover: 'hover:shadow-[0_0_0_1px_var(--color-accent)]',
  },
];

export function WelcomePage() {
  const navigate = useNavigate();
  const { setMode } = useActiveMode();
  const { clearPredictions } = usePredictions();
  const [selecting, setSelecting] = useState<ActiveMode | null>(null);

  const handleSelect = async (mode: Exclude<ActiveMode, 'none'>) => {
    if (selecting) return;
    setSelecting(mode);
    try {
      clearPredictions();
      await setMode(mode);
      // All modes route to the mode-specific workflow page
      navigate('/workflow');
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
          <p className="text-sm text-[var(--color-text-secondary)] max-w-sm mx-auto">
            Choose a source to begin. All predictions, scores, and reports are scoped to this source only.
            Use Reset at any time to switch.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {SOURCE_CARDS.map(({ mode, label, description, IconComponent, borderHover, ringHover }) => (
            <button
              key={mode}
              onClick={() => handleSelect(mode)}
              disabled={selecting !== null}
              className={`text-left bg-white border border-[var(--color-border)] rounded-2xl p-5 transition-all disabled:opacity-60 shadow-[0_1px_3px_rgba(0,0,0,0.08)] ${borderHover} ${ringHover}`}
            >
              <IconComponent />
              <h3 className="font-semibold text-sm mb-1 text-center">
                {selecting === mode ? 'Setting up…' : label}
              </h3>
              <p className="text-xs text-[var(--color-text-secondary)] text-center leading-relaxed">
                {description}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
