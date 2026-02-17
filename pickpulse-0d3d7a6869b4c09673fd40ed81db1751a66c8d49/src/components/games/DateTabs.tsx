import { DateFilter } from '@/types/sports';
import { cn } from '@/lib/utils';
import { Calendar } from 'lucide-react';
import { format, addDays } from 'date-fns';

interface DateTabsProps {
  selected: DateFilter;
  onChange: (date: DateFilter) => void;
}

export const DateTabs = ({ selected, onChange }: DateTabsProps) => {
  const today = new Date();
  
  const tabs: { value: DateFilter; label: string; date: Date }[] = [
    { value: 'today', label: 'Today', date: today },
    { value: 'tomorrow', label: 'Tomorrow', date: addDays(today, 1) },
    { value: 'nextDay', label: format(addDays(today, 2), 'EEE'), date: addDays(today, 2) },
  ];

  return (
    <div className="flex items-center gap-2 p-1 bg-muted rounded-xl">
      {tabs.map(({ value, label, date }) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
            selected === value
              ? 'bg-card text-foreground shadow-sm'
              : 'text-muted-foreground hover:text-foreground'
          )}
        >
          <Calendar className="h-4 w-4" />
          <div className="flex flex-col items-start">
            <span>{label}</span>
            <span className="text-xs opacity-60">{format(date, 'MMM d')}</span>
          </div>
        </button>
      ))}
    </div>
  );
};
