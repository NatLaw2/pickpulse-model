import { useEffect, useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { api, type ApiDocsResponse, type ApiEndpoint } from '../lib/api';

export function ApiDocsPage() {
  const [docs, setDocs] = useState<ApiDocsResponse | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  useEffect(() => {
    api.apiDocs().then(setDocs).catch(console.error);
  }, []);

  const copyToClipboard = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const methodColor = (m: string) => {
    if (m === 'GET') return '#2DD4BF';
    if (m === 'POST') return '#7B61FF';
    if (m === 'PUT') return '#FBBF24';
    if (m === 'DELETE') return '#FB7185';
    return 'rgba(255,255,255,0.55)';
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Integration API</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">
          REST endpoints for embedding churn intelligence into your existing tools and workflows
        </p>
      </div>

      {docs && (
        <div className="space-y-4">
          <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl p-5 shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
            <div className="text-xs text-[var(--color-text-muted)] mb-1">Base URL</div>
            <code className="text-sm font-mono text-[var(--color-accent-glow)]">{docs.base_url}</code>
          </div>

          {docs.endpoints.map((ep, i) => (
            <EndpointCard key={i} ep={ep} idx={i} copiedIdx={copiedIdx} onCopy={copyToClipboard} methodColor={methodColor} />
          ))}
        </div>
      )}
    </div>
  );
}

function EndpointCard({
  ep, idx, copiedIdx, onCopy, methodColor,
}: {
  ep: ApiEndpoint;
  idx: number;
  copiedIdx: number | null;
  onCopy: (text: string, idx: number) => void;
  methodColor: (m: string) => string;
}) {
  return (
    <div className="bg-[var(--color-bg-card)] border border-[var(--color-border)] rounded-2xl overflow-hidden shadow-[0_10px_30px_rgba(0,0,0,0.35)]">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-[var(--color-border)]">
        <span
          className="px-2 py-0.5 rounded-lg text-xs font-bold"
          style={{ background: `${methodColor(ep.method)}20`, color: methodColor(ep.method) }}
        >
          {ep.method}
        </span>
        <code className="text-sm font-mono">{ep.path}</code>
        <span className="text-xs text-[var(--color-text-secondary)] ml-auto">{ep.description}</span>
      </div>

      {ep.curl && (
        <div className="px-5 py-3 bg-[rgba(255,255,255,0.02)] relative group">
          <pre className="text-xs font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap">{ep.curl}</pre>
          <button
            onClick={() => onCopy(ep.curl!, idx)}
            className="absolute top-2 right-3 p-1.5 rounded-lg bg-[var(--color-bg-card)] border border-[var(--color-border)] opacity-0 group-hover:opacity-100 transition-opacity"
          >
            {copiedIdx === idx ? <Check size={12} className="text-[var(--color-success)]" /> : <Copy size={12} />}
          </button>
        </div>
      )}

      {ep.response_example && (
        <details className="px-5 py-3 border-t border-[var(--color-border)]">
          <summary className="text-xs text-[var(--color-text-muted)] cursor-pointer">Response Example</summary>
          <pre className="mt-2 text-xs font-mono text-[var(--color-text-secondary)] whitespace-pre-wrap">
            {JSON.stringify(ep.response_example, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
