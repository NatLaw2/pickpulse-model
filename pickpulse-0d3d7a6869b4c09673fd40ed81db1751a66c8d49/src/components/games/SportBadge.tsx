import { forwardRef } from 'react';
import { Sport, SPORT_LABELS } from '@/types/sports';
import { cn } from '@/lib/utils';

interface SportBadgeProps {
  sport: Sport;
  size?: 'sm' | 'md';
}

export const SportBadge = forwardRef<HTMLSpanElement, SportBadgeProps>(
  ({ sport, size = 'md' }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(
          'sport-badge',
          `sport-badge-${sport}`,
          size === 'sm' && 'text-[10px] px-2 py-0.5'
        )}
      >
        {SPORT_LABELS[sport]}
      </span>
    );
  }
);

SportBadge.displayName = 'SportBadge';
