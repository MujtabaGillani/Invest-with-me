import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { InvestorProfile, InvestorProfileInput } from '@/types';

/**
 * The investor profile - the user's own goals and risk limits.
 *
 * `GET /profile` answers 204 when no profile has been written, which the API
 * client turns into `null`. That is a meaningful state, not an error: it means the
 * user has not done the guide's first step yet, and several screens prompt for it.
 */

export function useProfile() {
  return useQuery({
    queryKey: queryKeys.profile,
    queryFn: () => api.get<InvestorProfile | null>('/profile'),
  });
}

export function useSaveProfile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: InvestorProfileInput) => api.put<InvestorProfile>('/profile', payload),
    onSuccess: (profile) => {
      queryClient.setQueryData(queryKeys.profile, profile);

      // The profile's limits feed position sizing, concentration warnings and
      // the technical framing note, so everything derived from it is now stale.
      // Invalidating broadly is correct here: this mutation is rare and getting
      // it wrong would leave the user looking at warnings from their old limits.
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.plans.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
      void queryClient.invalidateQueries({ queryKey: ['companies', 'technicals'] });
    },
  });
}
