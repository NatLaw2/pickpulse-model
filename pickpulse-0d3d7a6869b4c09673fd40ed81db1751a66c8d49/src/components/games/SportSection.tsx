import { Game, Sport, SPORT_LABELS } from '@/types/sports';
import { GameCard } from './GameCard';
import { SportBadge } from './SportBadge';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

interface SportSectionProps {
  sport: Sport;
  games: Game[];
}

export const SportSection = ({ sport, games }: SportSectionProps) => {
  const [collapsed, setCollapsed] = useState(false);

  if (games.length === 0) {
    return null;
  }

  return (
    <section className="mb-8">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between gap-4 mb-4 group"
      >
        <div className="flex items-center gap-3">
          <SportBadge sport={sport} />
          <span className="text-sm text-muted-foreground">
            {games.length} {games.length === 1 ? 'game' : 'games'}
          </span>
        </div>
        <div className="flex items-center gap-2 text-muted-foreground group-hover:text-foreground transition-colors">
          <span className="text-sm">{collapsed ? 'Show' : 'Hide'}</span>
          {collapsed ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronUp className="h-4 w-4" />
          )}
        </div>
      </button>

      {!collapsed && (
        <div className="space-y-3 animate-fade-in">
          {games.map((game) => (
            <GameCard key={game.id} game={game} />
          ))}
        </div>
      )}
    </section>
  );
};
