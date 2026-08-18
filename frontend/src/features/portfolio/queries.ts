import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { Portfolio, Trade, TradeInput } from '@/types';

/**
 * Portfolio and the trade ledger.
 *
 * Holdings are derived server-side from the ledger on every request, so there is
 * nothing to keep in sync client-side - recording a trade simply invalidates the
 * portfolio query and the next render is correct by construction.
 */

export const TRADES_PAGE_SIZE = 50;

export function usePortfolio() {
  return useQuery({
    queryKey: queryKeys.portfolio.all,
    queryFn: () => api.get<Portfolio>('/portfolio'),
  });
}

export function useTrades(limit = TRADES_PAGE_SIZE) {
  return useQuery({
    queryKey: queryKeys.portfolio.trades(limit),
    queryFn: () => api.get<Trade[]>('/portfolio/trades', { limit }),
  });
}

export function useRecordTrade() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: TradeInput) => api.post<Trade>('/portfolio/trades', payload),
    onSuccess: () => {
      // A trade changes the portfolio, the ledger, and - because a buy against a
      // committed plan marks that plan executed - the plans too. It also moves
      // every weight, so concentration alerts may have changed.
      void queryClient.invalidateQueries({ queryKey: queryKeys.portfolio.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.plans.all });
      void queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all });
    },
  });
}
