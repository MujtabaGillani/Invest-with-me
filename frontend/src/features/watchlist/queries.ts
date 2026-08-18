import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { WatchlistItem, WatchlistItemInput, WatchlistItemPatch } from '@/types';

/** Companies being researched but not yet owned. */

export function useWatchlist() {
  return useQuery({
    queryKey: queryKeys.watchlist.all,
    queryFn: () => api.get<WatchlistItem[]>('/watchlist'),
  });
}

export function useAddToWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: WatchlistItemInput) => api.post<WatchlistItem>('/watchlist', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist.all });
      // A watched company at or below its noted entry price raises an alert.
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useUpdateWatchlistItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: WatchlistItemPatch }) =>
      api.patch<WatchlistItem>(`/watchlist/${id}`, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useRemoveFromWatchlist() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => api.delete<null>(`/watchlist/${id}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}
