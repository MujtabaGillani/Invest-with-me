import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { BuyCandidates, PortfolioHistory, SellReview } from '@/types';

/**
 * The simplified buy/sell screen.
 *
 * All three are read-only server computations - a ranked shortlist, the exit rules
 * that have been crossed, and the invested/value series. Nothing is cached
 * aggressively: the whole point of these screens is that they reflect the latest
 * stored price, and a stale shortlist is worse than a slow one.
 */

export function useBuyCandidates(limit = 10) {
  return useQuery({
    queryKey: queryKeys.screener.buyCandidates(limit),
    queryFn: () => api.get<BuyCandidates>('/screener/buy-candidates', { limit }),
  });
}

export function useSellReview() {
  return useQuery({
    queryKey: queryKeys.screener.sellReview,
    queryFn: () => api.get<SellReview>('/screener/sell-review'),
  });
}

export function usePortfolioHistory() {
  return useQuery({
    queryKey: queryKeys.portfolio.history,
    queryFn: () => api.get<PortfolioHistory>('/portfolio/history'),
  });
}
