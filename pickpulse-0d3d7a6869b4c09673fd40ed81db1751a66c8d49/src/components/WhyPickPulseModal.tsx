// src/components/WhyPickPulseModal.tsx
import * as React from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

type WhyPickPulseModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function WhyPickPulseModal({ open, onOpenChange }: WhyPickPulseModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>Why PickPulse</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 text-sm text-muted-foreground leading-relaxed">
          <p className="text-foreground">
            PickPulse surfaces only the bets that survive both <span className="font-medium">model logic</span> and{" "}
            <span className="font-medium">market reality</span>.
          </p>

          <div className="border-t border-border pt-4 space-y-3">
            <p>
              Most betting tools flood you with picks.{" "}
              <span className="text-foreground">PickPulse does the opposite.</span>
            </p>

            <p>Every play shown here passes two filters:</p>

            <div className="space-y-3">
              <div className="rounded-lg border border-border bg-background/40 p-3">
                <div className="text-foreground font-medium">1) Model confidence</div>
                <div className="mt-1">
                  We only elevate bets when the underlying signal clears a meaningful bar — no forced daily picks.
                </div>
              </div>

              <div className="rounded-lg border border-border bg-background/40 p-3">
                <div className="text-foreground font-medium">2) Market validation</div>
                <div className="mt-1">
                  We sanity-check against the market so confidence stays realistic — not everything is “95%.”
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-4 space-y-2">
            <p className="text-foreground font-medium">What this means in practice:</p>
            <ul className="list-disc pl-5 space-y-1">
              <li>Fewer bets</li>
              <li>No inflated confidence</li>
              <li>No parlays or hype</li>
              <li>Clear reasons for what made the cut</li>
            </ul>
          </div>

          <div className="border-t border-border pt-4">
            <p className="text-foreground font-medium">Fewer bets. Better reasons. Clearer decisions.</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default WhyPickPulseModal;
