import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Upload } from 'lucide-react';
import { useActiveMode, type ActiveMode } from '../lib/ActiveModeContext';
import { usePredictions } from '../lib/PredictionContext';

// ---------------------------------------------------------------------------
// Source card definitions
// ---------------------------------------------------------------------------

type SourceCard = {
  mode: Exclude<ActiveMode, 'none'>;
  label: string;
  description: string;
  borderHover: string;
  ringHover: string;
} & (
  | { kind: 'wordmark'; wordmarkSrc: string; wordmarkAlt: string }
  | { kind: 'icon'; icon: () => React.ReactElement }
);

const SOURCE_CARDS: SourceCard[] = [
  {
    mode: 'salesforce',
    kind: 'wordmark',
    label: 'Salesforce',
    wordmarkSrc: '/logos/salesforce-wordmark.png',
    wordmarkAlt: 'Salesforce',
    description: 'Sync accounts and engagement signals directly from your Salesforce CRM.',
    borderHover: 'hover:border-[#00A1E0]/50',
    ringHover: 'hover:shadow-[0_0_0_1px_rgba(0,161,224,0.35)]',
  },
  {
    mode: 'hubspot',
    kind: 'wordmark',
    label: 'HubSpot',
    wordmarkSrc: '/logos/hubspot-wordmark.png',
    wordmarkAlt: 'HubSpot',
    description: 'Pull contacts, deals, and activity directly from HubSpot.',
    borderHover: 'hover:border-[#FF7A59]/50',
    ringHover: 'hover:shadow-[0_0_0_1px_rgba(255,122,89,0.35)]',
  },
  {
    mode: 'csv',
    kind: 'icon',
    label: 'Upload CSV',
    icon: () => (
      <div className="w-12 h-12 rounded-2xl bg-[var(--color-accent)]/12 flex items-center justify-center mx-auto">
        <Upload size={24} className="text-[var(--color-accent)]" />
      </div>
    ),
    description: 'Upload your own customer data file to generate churn predictions.',
    borderHover: 'hover:border-[var(--color-accent)]',
    ringHover: 'hover:shadow-[0_0_0_1px_var(--color-accent)]',
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function WelcomePage() {
  const navigate = useNavigate();
  const { setMode } = useActiveMode();
  const { clearPredictions } = usePredictions();
  const [selecting, setSelecting] = useState<Exclude<ActiveMode, 'none'> | null>(null);

  const handleSelect = async (mode: Exclude<ActiveMode, 'none'>) => {
    if (selecting) return;
    setSelecting(mode);
    try {
      clearPredictions();
      await setMode(mode);
      navigate('/workflow');
    } catch {
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
          {SOURCE_CARDS.map((card) => (
            <button
              key={card.mode}
              onClick={() => handleSelect(card.mode)}
              disabled={selecting !== null}
              className={`bg-white border border-[var(--color-border)] rounded-2xl p-6 transition-all disabled:opacity-60 shadow-[0_1px_3px_rgba(0,0,0,0.08)] ${card.borderHover} ${card.ringHover}`}
            >
              {/* Logo / icon area */}
              <div className="flex items-center justify-center mb-4" style={{ minHeight: 64 }}>
                {card.kind === 'wordmark' ? (
                  <img
                    src={card.wordmarkSrc}
                    alt={card.wordmarkAlt}
                    className="max-h-14 w-auto max-w-full object-contain"
                    draggable={false}
                  />
                ) : (
                  card.icon()
                )}
              </div>

              {/* For wordmark cards the logo already contains the brand name;
                  show label only for non-wordmark cards or when loading. */}
              {card.kind === 'icon' && (
                <h3 className="font-semibold text-sm mb-1 text-center">{card.label}</h3>
              )}

              {/* Loading state */}
              {selecting === card.mode && (
                <p className="text-xs text-center text-[var(--color-accent)] font-medium flex items-center justify-center gap-1 mb-1">
                  <Loader2 size={11} className="animate-spin" />
                  Setting up…
                </p>
              )}

              <p className="text-xs text-[var(--color-text-secondary)] text-center leading-relaxed">
                {card.description}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
