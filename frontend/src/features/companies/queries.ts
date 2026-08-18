import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { CompanyDetail, CompanyPage, PriceHistory } from '@/types';

/** Company browsing and raw market data. */

export interface CompanyListFilters {
  search?: string | undefined;
  sector?: string | undefined;
  limit?: number | undefined;
  offset?: number | undefined;
}

export const COMPANIES_PAGE_SIZE = 25;

function fetchCompanies(filters: CompanyListFilters): Promise<CompanyPage> {
  return api.get<CompanyPage>('/companies', {
    search: filters.search,
    sector: filters.sector,
    limit: filters.limit ?? COMPANIES_PAGE_SIZE,
    offset: filters.offset ?? 0,
  });
}

export function useCompanies(filters: CompanyListFilters) {
  return useQuery({
    queryKey: queryKeys.companies.list(filters),
    queryFn: () => fetchCompanies(filters),
    // Keeps the previous page visible while the next one loads, so paging and
    // typing in the search box do not blank the table on every keystroke.
    placeholderData: (previous) => previous,
  });
}

export function useCompany(symbol: string | undefined) {
  return useQuery({
    queryKey: queryKeys.companies.detail(symbol ?? ''),
    queryFn: () => api.get<CompanyDetail>(`/companies/${symbol!}`),
    enabled: Boolean(symbol),
  });
}

/**
 * Stored daily price bars.
 *
 * @param sessions - how many of the most recent sessions to fetch. 260 is roughly
 *   a year of trading, which is the window the price chart shows.
 */
export function usePriceHistory(symbol: string | undefined, sessions = 260) {
  return useQuery({
    queryKey: queryKeys.companies.prices(symbol ?? '', sessions),
    queryFn: () => api.get<PriceHistory>(`/companies/${symbol!}/prices`, { sessions }),
    enabled: Boolean(symbol),
  });
}
