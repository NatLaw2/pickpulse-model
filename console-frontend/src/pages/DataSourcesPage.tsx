import { useState } from 'react';
import { DatasetsPage } from './DatasetsPage';
import { IntegrationsPage } from './IntegrationsPage';

const TABS = [
  { key: 'datasets', label: 'Datasets' },
  { key: 'integrations', label: 'Integrations' },
] as const;

type Tab = typeof TABS[number]['key'];

export function DataSourcesPage() {
  const [tab, setTab] = useState<Tab>('datasets');

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Data Sources</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          Connect your account data via CSV upload, demo datasets, or live integrations
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

      {/* Tab content */}
      <div className={tab === 'datasets' ? '' : 'hidden'}>
        <DatasetsPage embedded />
      </div>
      <div className={tab === 'integrations' ? '' : 'hidden'}>
        <IntegrationsPage embedded />
      </div>
    </div>
  );
}
