import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, Brain, CheckCircle2, Database, Loader2, XCircle } from 'lucide-react';
import { api, isNoDatasetError, type TrainJobStatus } from '../lib/api';
import { useDataset } from '../lib/DatasetContext';

const POLL_INTERVAL_MS = 3000;

export function TrainPage({ embedded }: { embedded?: boolean } = {}) {
  const [valFrac, setValFrac] = useState(0.2);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<TrainJobStatus | null>(null);
  const [error, setError] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const navigate = useNavigate();
  const { dataset } = useDataset();

  // Poll for job status while pending/running
  useEffect(() => {
    if (!jobId) return;
    if (jobStatus?.status === 'complete' || jobStatus?.status === 'failed') return;

    const poll = async () => {
      try {
        const status = await api.trainStatus(jobId);
        setJobStatus(status);
        if (status.status === 'complete' || status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.startsWith('404')) {
          // Job row not found — server may have restarted and lost the job.
          // Stop polling and surface the error so the user can retry.
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          setJobId(null);
          setJobStatus(null);
          setError('Training job not found — the server may have restarted. Please try again.');
        }
        // Other errors (5xx, network timeout) are transient — keep polling.
      }
    };

    poll(); // immediate first check
    pollRef.current = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [jobId, jobStatus?.status]);

  const handleTrain = async () => {
    setSubmitting(true);
    setError('');
    setJobId(null);
    setJobStatus(null);
    try {
      const res = await api.train(valFrac);
      setJobId(res.job_id);
      setJobStatus({ job_id: res.job_id, status: 'pending', version_str: null, metrics: null,
                     error_message: null, started_at: null, completed_at: null });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  };

  const noDataset = !dataset || (error && isNoDatasetError(error));
  const realError = error && !isNoDatasetError(error);
  const trainingBlocked = dataset && dataset.readiness_mode != null &&
    dataset.readiness_mode !== 'TRAINING_READY' && dataset.readiness_mode !== 'TRAINING_DEGRADED';
  const isRunning = jobStatus?.status === 'pending' || jobStatus?.status === 'running';
  const isComplete = jobStatus?.status === 'complete';
  const isFailed = jobStatus?.status === 'failed';
  const metrics = jobStatus?.metrics ?? null;

  return (
    <div>
      {!embedded && (
        <div className="mb-8">
          <h1 className="text-2xl font-bold">Train Model</h1>
          <p className="text-sm text-[var(--color-text-secondary)] mt-1">Build a calibrated churn prediction model from your account data</p>
        </div>
      )}

      {/* No dataset guidance */}
      {noDataset && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-8 mb-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <Database size={32} className="mx-auto mb-3 text-[var(--color-text-muted)]" />
          <h3 className="font-semibold mb-2">No dataset loaded</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Load a sample dataset or upload your own account data before training the model.
          </p>
          <button
            onClick={() => navigate('/data-sources')}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            Go to Datasets
          </button>
        </div>
      )}

      {/* Training not available — no churn label */}
      {!noDataset && trainingBlocked && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-8 mb-8 text-center shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <AlertTriangle size={32} className="mx-auto mb-3 text-amber-500" />
          <h3 className="font-semibold mb-2">Training requires a churn label</h3>
          <p className="text-sm text-[var(--color-text-secondary)] mb-5 max-w-md mx-auto">
            Your dataset is loaded in <strong>{dataset?.readiness_mode?.replace('_', ' ')}</strong> mode
            because no <code className="font-mono text-xs">churned</code> column was mapped.
            Return to Data Sources to re-upload with a churn outcome column, or map an existing column to <code className="font-mono text-xs">churned</code>.
          </p>
          <button
            onClick={() => navigate('/data-sources')}
            className="px-5 py-2.5 bg-[var(--color-accent)] text-white rounded-xl text-sm font-medium hover:bg-[var(--color-accent-glow)] transition-all shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            Go to Data Sources
          </button>
        </div>
      )}

      {/* Train form */}
      {!noDataset && !trainingBlocked && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-6 mb-5">
            <div>
              <label className="text-xs text-[var(--color-text-secondary)] block mb-1" title="Percentage of data held out for unbiased performance evaluation after training.">Validation Holdout</label>
              <select
                value={valFrac}
                onChange={(e) => setValFrac(Number(e.target.value))}
                disabled={isRunning}
                className="bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl px-3 py-2 text-sm disabled:opacity-50"
              >
                <option value={0.1}>10%</option>
                <option value={0.2}>20% (Recommended)</option>
                <option value={0.3}>30%</option>
              </select>
            </div>
          </div>

          <button
            onClick={handleTrain}
            disabled={submitting || isRunning}
            className="flex items-center gap-2 px-6 py-2.5 bg-[var(--color-accent)] text-white rounded-xl font-medium hover:bg-[var(--color-accent-glow)] transition-all disabled:opacity-50 shadow-[0_0_0_0_rgba(123,97,255,0)] hover:shadow-[0_0_0_4px_rgba(123,97,255,0.15)]"
          >
            {(submitting || isRunning) ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                {submitting ? 'Submitting…' : jobStatus?.status === 'pending' ? 'Queued…' : 'Training…'}
              </>
            ) : (
              <>
                <Brain size={16} />
                Train Churn Model
              </>
            )}
          </button>
        </div>
      )}

      {/* Job progress indicator */}
      {isRunning && (
        <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 mb-8 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
          <div className="flex items-center gap-3">
            <Loader2 size={18} className="animate-spin text-[var(--color-accent)]" />
            <div>
              <p className="text-sm font-medium">
                {jobStatus?.status === 'pending' ? 'Waiting to start…' : 'Training in progress…'}
              </p>
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                This runs in the background. You can navigate away and return — results will be here when complete.
              </p>
            </div>
          </div>
          {/* Progress bar — indeterminate */}
          <div className="mt-4 h-1.5 bg-[var(--color-bg-primary)] rounded-full overflow-hidden">
            <div className="h-full bg-[var(--color-accent)] rounded-full animate-[progress-slide_1.8s_ease-in-out_infinite]" style={{ width: '40%' }} />
          </div>
        </div>
      )}

      {/* Submission / validation error */}
      {realError && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-4 mb-6">
          <p className="text-sm text-[var(--color-danger)]">{error}</p>
        </div>
      )}

      {/* Training failure */}
      {isFailed && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 mb-6 flex items-start gap-3">
          <XCircle size={18} className="text-[var(--color-danger)] mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-semibold text-[var(--color-danger)]">Training failed</p>
            {jobStatus?.error_message && (
              <p className="text-xs text-[var(--color-danger)] mt-1 font-mono">{jobStatus.error_message}</p>
            )}
          </div>
        </div>
      )}

      {/* Training complete + results */}
      {isComplete && (
        <div className="space-y-6">
          <div className="bg-white border border-emerald-200 rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
            <div className="flex items-center gap-2 mb-4">
              <CheckCircle2 size={18} className="text-[var(--color-success)]" />
              <h3 className="font-semibold">Training Complete</h3>
              <span className="ml-2 font-mono text-sm text-[var(--color-accent)]">{jobStatus?.version_str}</span>
            </div>
          </div>

          {metrics && (
            <div className="bg-white border border-[var(--color-border)] rounded-2xl p-6 shadow-[0_1px_3px_rgba(0,0,0,0.08)]">
              <h3 className="font-semibold mb-4 text-sm">Validation Metrics</h3>
              <dl className="grid grid-cols-2 md:grid-cols-4 gap-6 text-sm">
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">AUC</dt>
                  <dd className="text-2xl font-bold text-[var(--color-success)]">{metrics.auc}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">PR-AUC</dt>
                  <dd className="text-2xl font-bold">{metrics.pr_auc}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">Brier Score</dt>
                  <dd className="text-2xl font-bold">{metrics.brier}</dd>
                </div>
                <div>
                  <dt className="text-[var(--color-text-muted)] text-xs mb-1">Log Loss</dt>
                  <dd className="text-2xl font-bold">{metrics.logloss}</dd>
                </div>
              </dl>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
