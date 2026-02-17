import { cn } from '@/lib/utils';

type TimeRange = '7d' | '30d' | 'season';

interface TimeRangeSelectorProps {
  selected: TimeRange;
  onChange: (range: TimeRange) => void;
}

const timeRanges: { value: TimeRange; label: string }[] = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: 'season', label: 'Season' },
];

export const TimeRangeSelector = ({
  selected,
  onChange,
}: TimeRangeSelectorProps) => {
  return (
    <div className="flex items-center gap-1 p-1 bg-muted rounded-lg">
      {timeRanges.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          className={cn(
            'px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-200',
            selected === value
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
};
