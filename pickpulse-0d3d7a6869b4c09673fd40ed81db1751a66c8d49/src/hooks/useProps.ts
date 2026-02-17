import { useQuery } from '@tanstack/react-query';
import { fetchProps } from '@/lib/api';
import { Sport } from '@/types/sports';

export function useProps(sportKey: Sport, eventId: string, enabled: boolean = true) {
  return useQuery({
    queryKey: ['props', sportKey, eventId],
    queryFn: () => fetchProps(sportKey, eventId),
    enabled: enabled && !!eventId,
    staleTime: 1000 * 60 * 5, // 5 minutes
    refetchOnWindowFocus: false,
  });
}
