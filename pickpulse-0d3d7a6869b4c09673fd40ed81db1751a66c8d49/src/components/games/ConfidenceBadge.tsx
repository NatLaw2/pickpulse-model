import { ConfidenceTier } from '@/types/sports';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface ConfidenceBadgeProps {
  confidence: ConfidenceTier;
}

const confidenceConfig = {
  high: {
    label: 'High Confidence',
    icon: TrendingUp,
  },
  medium: {
    label: 'Medium Confidence',
    icon: Minus,
  },
  low: {
    label: 'Low Confidence',
    icon: TrendingDown,
  },
};

export const ConfidenceBadge = ({ confidence }: ConfidenceBadgeProps) => {
  const config = confidenceConfig[confidence];
  const Icon = config.icon;

  return (
    <span className={cn('confidence-badge', `confidence-${confidence}`)}>
      <Icon className="h-3 w-3 mr-1" />
      {config.label}
    </span>
  );
};
