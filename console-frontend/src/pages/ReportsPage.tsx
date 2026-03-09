import { FileText, Download } from 'lucide-react';
import { api } from '../lib/api';

export function ReportsPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Reports</h1>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">Export presentation-ready reports and scored data for leadership review or CRM integration</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3 mb-3">
            <FileText size={24} className="text-[var(--color-accent)]" />
            <h3 className="font-semibold">PDF Churn Risk Report</h3>
          </div>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5">
            Executive summary with model discrimination metrics, lift analysis, calibration curves, risk tier breakdown,
            and projected business impact. Board-ready format.
          </p>
          <button
            onClick={() => api.downloadReport().catch((e: any) => alert(e.message))}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            <Download size={14} />
            Download PDF
          </button>
        </div>

        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3 mb-3">
            <FileText size={24} className="text-[var(--color-success)]" />
            <h3 className="font-semibold">Scored Predictions CSV</h3>
          </div>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5">
            Complete scored dataset with churn probabilities, urgency rankings, renewal windows, ARR at risk,
            and recommended next actions. Import directly into Salesforce, HubSpot, or your BI platform.
          </p>
          <button
            onClick={() => api.exportPredictions().catch((e: any) => alert(e.message))}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl text-sm hover:bg-[var(--color-bg-primary)] transition-colors"
          >
            <Download size={14} />
            Download CSV
          </button>
        </div>
      </div>
    </div>
  );
}
