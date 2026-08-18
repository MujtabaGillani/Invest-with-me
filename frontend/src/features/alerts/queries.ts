import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { Alert, AlertEvaluation, MessageResponse } from '@/types';

/**
 * Alerts - the user's own pre-committed rules crossing their thresholds.
 *
 * Listing is read-only and reports what the last evaluation found. Re-checking the
 * portfolio is an explicit mutation (`POST /alerts/evaluate`), which is why it is
 * modelled as one here rather than being fired on mount: a GET must not write, and
 * the user gets a summary of what changed instead of a silently different list.
 */

export function useAlerts(includeAcknowledged = false) {
  return useQuery({
    queryKey: queryKeys.alerts.list(includeAcknowledged),
    queryFn: () => api.get<Alert[]>('/alerts', { include_acknowledged: includeAcknowledged }),
  });
}

/** Unacknowledged count, for the navigation badge. */
export function useOpenAlertCount(): number {
  const { data } = useAlerts(false);
  return data?.length ?? 0;
}

export function useEvaluateAlerts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<AlertEvaluation>('/alerts/evaluate'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => api.post<Alert>(`/alerts/${id}/acknowledge`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}

export function useAcknowledgeAllAlerts() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<MessageResponse>('/alerts/acknowledge-all'),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}
