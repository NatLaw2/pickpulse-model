import { useState } from 'react';
import { TrainPage } from './TrainPage';
import { EvaluatePage } from './EvaluatePage';

const TABS = [
  { key: 'train', label: 'Train' },
  { key: 'performance', label: 'Performance' },
] as const;

type Tab = typeof TABS[number]['key'];

export function ModelPage() {
  const [tab, setTab] = useState<Tab>('train');

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Performance</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          Review model health, training history, and prediction accuracy
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-8 border-b border-[var(--color-border)]">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2.5 text-sm font-medium transition-colors relative ${
              tab === t.key
                ? 'text-[var(--color-accent)]'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)]'
            }`}
          >
            {t.label}
            {tab === t.key && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-accent)] rounded-t" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content — hide the duplicate page headers */}
      <div className={tab === 'train' ? '' : 'hidden'}>
        <TrainPage embedded />
      </div>
      <div className={tab === 'performance' ? '' : 'hidden'}>
        <EvaluatePage embedded />
      </div>
    </div>
  );
}
