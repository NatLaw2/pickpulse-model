import { useQuery } from '@tanstack/react-query';
import { fetchSlate } from '@/lib/api';
import { DateFilter, Game, Sport } from '@/types/sports';

export function useSlate(dateFilter: DateFilter) {
  return useQuery({
    queryKey: ['slate', dateFilter],
    queryFn: () => fetchSlate(dateFilter),
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchOnWindowFocus: false,
  });
}

export function useSlateForSport(dateFilter: DateFilter, sport: Sport) {
  const { data, isLoading, error } = useSlate(dateFilter);
  
  return {
    games: data?.[sport] ?? [],
    isLoading,
    error,
  };
}
