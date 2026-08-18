import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { FundamentalsReport, TechnicalReport } from '@/types';

/**
 * Analysis reports.
 *
 * Both endpoints legitimately return 422 `insufficient_data` - a company with no
 * filings loaded, or too little price history for a 200-day average. The query
 * client already declines to retry 4xx responses, so the component receives that
 * error once and can render the explanation the server supplied rather than
 * spinning.
 */

export function useFundamentals(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.companies.fundamentals(symbol ?? ''),
    queryFn: () => api.get<FundamentalsReport>(`/companies/${symbol!}/fundamentals`),
    enabled: Boolean(symbol),
  });
}

export function useTechnicals(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.companies.technicals(symbol ?? ''),
    queryFn: () => api.get<TechnicalReport>(`/companies/${symbol!}/technicals`),
    enabled: Boolean(symbol),
  });
}
