import { AlertTriangle, Phone } from 'lucide-react';

export const Footer = () => {
  return (
    <footer className="mt-auto border-t border-border bg-card">
      <div className="container py-6">
        {/* Compliance Disclaimer */}
        <div className="flex flex-col md:flex-row items-start md:items-center gap-4 p-4 rounded-lg bg-muted/50 border border-border mb-4">
          <div className="flex items-center gap-2 text-accent">
            <AlertTriangle className="h-5 w-5 flex-shrink-0" />
            <span className="font-semibold text-sm">Disclaimer</span>
          </div>
          <p className="text-sm text-muted-foreground leading-relaxed">
            All picks are opinions provided for informational and entertainment purposes only. 
            Past performance does not guarantee future results. This site does not facilitate 
            or encourage gambling. Please gamble responsibly and only where it is legal.
          </p>
        </div>

        {/* Helpline Notice */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 p-3 rounded-lg bg-accent/5 border border-accent/20 mb-6">
          <div className="flex items-center gap-2 text-accent">
            <Phone className="h-4 w-4 flex-shrink-0" />
            <span className="text-sm font-medium">Problem Gambling Helpline:</span>
          </div>
          <a 
            href="tel:1-800-522-4700" 
            className="text-sm font-mono font-semibold text-foreground hover:text-primary transition-colors"
          >
            1-800-522-4700
          </a>
          <span className="text-xs text-muted-foreground">(24/7 • Confidential • Free)</span>
        </div>

        <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
          <p>© 2025 PickPulse. All rights reserved.</p>
          <div className="flex items-center gap-6">
            <a href="/about" className="hover:text-foreground transition-colors">About & Disclaimer</a>
            <a href="#" className="hover:text-foreground transition-colors">Privacy Policy</a>
            <a href="#" className="hover:text-foreground transition-colors">Terms of Service</a>
          </div>
        </div>
      </div>
    </footer>
  );
};
