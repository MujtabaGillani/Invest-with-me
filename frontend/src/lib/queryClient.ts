import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './apiClient';

/**
 * React Query configuration.
 *
 * Two decisions worth stating:
 *
 * **Retries are selective.** Retrying a 404 or a 422 is pointless - the answer
 * will not change - and retrying a 409 can make a duplicate-submission problem
 * worse. Only transport failures and 5xx are retried.
 *
 * **`staleTime` is 30 seconds.** The underlying data is end-of-day prices and
 * annual filings, so refetching on every window focus would be pure noise. It is
 * deliberately not longer: after recording a trade the user expects the portfolio
 * to move, and that path uses explicit invalidation rather than waiting for a
 * timer.
 */
export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError) {
            // A client error is a settled answer; retrying just delays the
            // message the user needs to see.
            if (error.status >= 400 && error.status < 500) return false;
          }
          return failureCount < 2;
        },
      },
      mutations: {
        // Never retry a mutation automatically. Every mutation here records a
        // decision or a trade, and a silent second attempt could duplicate one.
        retry: false,
      },
    },
  });
}
