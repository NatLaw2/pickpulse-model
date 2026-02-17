import { AlertTriangle, BarChart3, Shield, Users, Phone, ExternalLink } from 'lucide-react';

export const AboutPage = () => {
  return (
    <div className="container py-8 max-w-4xl">
      <div className="mb-12">
        <h1 className="text-3xl font-bold text-foreground mb-4">
          About PickPulse
        </h1>
        <p className="text-lg text-muted-foreground leading-relaxed">
          PickPulse is a sports analytics platform providing data-driven insights
          and predictions for major professional and collegiate sports.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
        <div className="stat-card">
          <div className="p-3 rounded-lg bg-primary/10 w-fit mb-4">
            <BarChart3 className="h-6 w-6 text-primary" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            Data-Driven Analysis
          </h3>
          <p className="text-muted-foreground text-sm leading-relaxed">
            Our predictions are generated using advanced statistical models,
            historical data, and real-time performance metrics.
          </p>
        </div>

        <div className="stat-card">
          <div className="p-3 rounded-lg bg-primary/10 w-fit mb-4">
            <Shield className="h-6 w-6 text-primary" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            Transparent Performance
          </h3>
          <p className="text-muted-foreground text-sm leading-relaxed">
            We track and display all our picks with complete transparency.
            View our historical accuracy across all sports and bet types.
          </p>
        </div>

        <div className="stat-card">
          <div className="p-3 rounded-lg bg-primary/10 w-fit mb-4">
            <Users className="h-6 w-6 text-primary" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            Expert Insights
          </h3>
          <p className="text-muted-foreground text-sm leading-relaxed">
            Each pick includes detailed analysis and reasoning, helping you
            understand the factors driving our predictions.
          </p>
        </div>

        <div className="stat-card">
          <div className="p-3 rounded-lg bg-accent/10 w-fit mb-4">
            <AlertTriangle className="h-6 w-6 text-accent" />
          </div>
          <h3 className="text-lg font-semibold text-foreground mb-2">
            Responsible Gaming
          </h3>
          <p className="text-muted-foreground text-sm leading-relaxed">
            We provide information for entertainment purposes only. We do not
            facilitate gambling or handle any wagering.
          </p>
        </div>
      </div>

      {/* Important Disclaimer */}
      <div className="bg-card rounded-2xl border border-border p-8 mb-8">
        <div className="flex items-start gap-4 mb-6">
          <div className="p-3 rounded-lg bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground mb-2">
              Important Disclaimer
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Please read and understand the following before using PickPulse.
            </p>
          </div>
        </div>

        <div className="space-y-4 text-sm text-muted-foreground">
          <p className="leading-relaxed">
            <strong className="text-foreground">For Entertainment Only:</strong>{' '}
            All picks, predictions, and analysis provided on PickPulse are
            opinions intended for informational and entertainment purposes only.
            They should not be construed as professional advice or guarantees of
            any kind.
          </p>

          <p className="leading-relaxed">
            <strong className="text-foreground">No Guarantee of Results:</strong>{' '}
            Past performance does not guarantee future results. Sports outcomes
            are inherently unpredictable, and no prediction system can guarantee
            accuracy.
          </p>

          <p className="leading-relaxed">
            <strong className="text-foreground">Not a Gambling Platform:</strong>{' '}
            PickPulse does not accept wagers, process payments, or facilitate
            gambling in any way. Links to external sportsbooks are provided for
            informational convenience only and do not constitute endorsement.
          </p>

          <p className="leading-relaxed">
            <strong className="text-foreground">Legal Compliance:</strong>{' '}
            Users are responsible for understanding and complying with all
            applicable laws and regulations regarding sports betting in their
            jurisdiction.
          </p>

          <p className="leading-relaxed">
            <strong className="text-foreground">Gamble Responsibly:</strong>{' '}
            If you choose to gamble, please do so responsibly and only where it
            is legal in your jurisdiction. Set limits, never chase losses, and
            only wager what you can afford to lose.
          </p>
        </div>
      </div>

      {/* Responsible Gaming Resources */}
      <div className="bg-card rounded-2xl border border-accent/30 p-8">
        <div className="flex items-start gap-4 mb-6">
          <div className="p-3 rounded-lg bg-accent/10">
            <Phone className="h-6 w-6 text-accent" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground mb-2">
              Responsible Gaming Resources
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              If you or someone you know has a gambling problem, help is available.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="p-4 rounded-lg bg-muted/50 border border-border">
            <p className="text-sm font-semibold text-foreground mb-1">
              National Problem Gambling Helpline
            </p>
            <p className="text-2xl font-bold font-mono text-primary mb-2">
              1-800-522-4700
            </p>
            <p className="text-xs text-muted-foreground">
              Available 24/7 • Confidential • Free
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <a
              href="https://www.ncpgambling.org"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-3 rounded-lg bg-muted/30 border border-border hover:bg-muted/50 transition-colors"
            >
              <span className="text-sm text-foreground">National Council on Problem Gambling</span>
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
            </a>
            <a
              href="https://www.gamblersanonymous.org"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 p-3 rounded-lg bg-muted/30 border border-border hover:bg-muted/50 transition-colors"
            >
              <span className="text-sm text-foreground">Gamblers Anonymous</span>
              <ExternalLink className="h-3.5 w-3.5 text-muted-foreground" />
            </a>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed">
            Gambling should be entertaining, not a source of stress or financial hardship.
            If gambling is no longer fun, it may be time to seek help. Remember: you are
            not alone, and support is available.
          </p>
        </div>
      </div>
    </div>
  );
};

export default AboutPage;
