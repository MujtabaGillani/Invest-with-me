import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type {
  PlanReviewInput,
  TradePlanDetail,
  TradePlanInput,
  TradePlanPage,
  TradePlanPatch,
} from '@/types';

/**
 * Trade plans - the pre-buy checklist and the exit rules.
 *
 * Two things shape this module:
 *
 * **Every mutation returns the full plan**, including its recomputed `readiness`.
 * So each one seeds the detail cache from the response rather than refetching,
 * which is what makes answering a checklist question feel immediate: the blocking
 * reasons update in the same tick.
 *
 * **Committing is expected to fail.** A 422 with `blocking_reasons` is the normal
 * outcome for an incomplete plan, not an exception - the component reads
 * `ApiError.blockingReasons` and lists them.
 */

export interface PlanListFilters {
  status?: string | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
}

export const PLANS_PAGE_SIZE = 25;

export function usePlans(filters: PlanListFilters = {}) {
  return useQuery({
    queryKey: queryKeys.plans.list(filters),
    queryFn: () =>
      api.get<TradePlanPage>('/plans', {
        plan_status: filters.status,
        limit: filters.limit ?? PLANS_PAGE_SIZE,
        offset: filters.offset ?? 0,
      }),
    placeholderData: (previous) => previous,
  });
}

export function usePlan(planId: number | undefined) {
  return useQuery({
    queryKey: queryKeys.plans.detail(planId ?? 0),
    queryFn: () => api.get<TradePlanDetail>(`/plans/${planId!}`),
    enabled: Boolean(planId),
  });
}

/**
 * Shared success handling for every plan mutation.
 *
 * Seeds the detail cache from the response and invalidates the lists. Also
 * invalidates the watchlist, because a watchlist row shows whether a plan already
 * exists for that company.
 */
function usePlanMutationCallbacks() {
  const queryClient = useQueryClient();

  return (plan: TradePlanDetail) => {
    queryClient.setQueryData(queryKeys.plans.detail(plan.id), plan);
    void queryClient.invalidateQueries({ queryKey: queryKeys.plans.all });
    void queryClient.invalidateQueries({ queryKey: queryKeys.watchlist.all });
  };
}

export function useCreatePlan() {
  const onPlanChanged = usePlanMutationCallbacks();

  return useMutation({
    mutationFn: (payload: TradePlanInput) => api.post<TradePlanDetail>('/plans', payload),
    onSuccess: onPlanChanged,
  });
}

export function useUpdatePlan() {
  const onPlanChanged = usePlanMutationCallbacks();

  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: TradePlanPatch }) =>
      api.patch<TradePlanDetail>(`/plans/${id}`, patch),
    onSuccess: onPlanChanged,
  });
}

export function useCommitPlan() {
  const onPlanChanged = usePlanMutationCallbacks();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => api.post<TradePlanDetail>(`/plans/${id}/commit`),
    onSuccess: (plan) => {
      onPlanChanged(plan);
      // A committed plan's exit rules apply the moment a buy is recorded, and the
      // portfolio shows those levels per holding.
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio.all });
    },
  });
}

export function useAbandonPlan() {
  const onPlanChanged = usePlanMutationCallbacks();

  return useMutation({
    mutationFn: ({ id, reason }: { id: number; reason?: string }) =>
      api.post<TradePlanDetail>(`/plans/${id}/abandon`, { reason: reason ?? null }),
    onSuccess: onPlanChanged,
  });
}

export function useClosePlan() {
  const onPlanChanged = usePlanMutationCallbacks();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => api.post<TradePlanDetail>(`/plans/${id}/close`),
    onSuccess: (plan) => {
      onPlanChanged(plan);
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio.all });
    },
  });
}

export function useRecordReview() {
  const onPlanChanged = usePlanMutationCallbacks();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, review }: { id: number; review: PlanReviewInput }) =>
      api.post<TradePlanDetail>(`/plans/${id}/reviews`, review),
    onSuccess: (plan) => {
      onPlanChanged(plan);
      // Recording a review clears the review-due alert.
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio.all });
    },
  });
}
