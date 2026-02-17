import { AlertTriangle } from "lucide-react";

export function HealthBanner({ reason, detail }: { reason: string; detail?: string }) {
  return (
    <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-2 text-sm text-amber-700">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4" />
        <span className="font-medium">{reason}</span>
      </div>
      {detail && <div className="mt-1 text-xs opacity-70">{detail}</div>}
    </div>
  );
}
