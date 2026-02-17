import { SportPerformance, SPORT_LABELS } from '@/types/sports';
import { SportBadge } from '../games/SportBadge';
import { StatCard } from './StatCard';
import { TrendingUp, Target, ArrowUpDown, Layers } from 'lucide-react';

interface SportPerformanceCardProps {
  performance: SportPerformance;
}

export const SportPerformanceCard = ({
  performance,
}: SportPerformanceCardProps) => {
  return (
    <div className="bg-card rounded-2xl border border-border overflow-hidden">
      <div className="p-6 border-b border-border">
        <div className="flex items-center justify-between">
          <SportBadge sport={performance.sport} />
          <div className="text-right">
            <p className="text-2xl font-bold text-foreground font-mono">
              {performance.overall.percentage}%
            </p>
            <p className="text-sm text-muted-foreground">
              {performance.totalPicks} total picks
            </p>
          </div>
        </div>
      </div>

      <div className="p-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <StatCard
          label="Moneyline"
          percentage={performance.moneyline.percentage}
          wins={performance.moneyline.wins}
          losses={performance.moneyline.losses}
        />
        <StatCard
          label="Spread"
          percentage={performance.spread.percentage}
          wins={performance.spread.wins}
          losses={performance.spread.losses}
        />
        <StatCard
          label="Over/Under"
          percentage={performance.overUnder.percentage}
          wins={performance.overUnder.wins}
          losses={performance.overUnder.losses}
        />
        <StatCard
          label="Parlays"
          percentage={performance.parlays.percentage}
          wins={performance.parlays.wins}
          losses={performance.parlays.losses}
        />
      </div>
    </div>
  );
};
