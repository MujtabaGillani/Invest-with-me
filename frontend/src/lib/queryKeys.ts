/**
 * Query key factory.
 *
 * Every React Query key is built here rather than written inline. The reason is
 * invalidation: after recording a trade, the portfolio, the alerts and possibly a
 * plan all become stale. Hand-written keys drift from the ones used to fetch, and
 * the symptom is a screen that silently shows old data - the hardest class of bug
 * to notice in a financial tool.
 *
 * Keys are hierarchical, so `invalidateQueries({ queryKey: queryKeys.plans.all })`
 * clears every plan query including individual ones.
 */

export const queryKeys = {
  meta: ['meta'] as const,
  health: ['health'] as const,

  companies: {
    all: ['companies'] as const,
    list: (filters: {
      search?: string | undefined;
      sector?: string | undefined;
      limit?: number | undefined;
      offset?: number | undefined;
    }) => ['companies', 'list', filters] as const,
    detail: (symbol: string) => ['companies', 'detail', symbol] as const,
    prices: (symbol: string, sessions: number) =>
      ['companies', 'prices', symbol, sessions] as const,
    fundamentals: (symbol: string) => ['companies', 'fundamentals', symbol] as const,
    technicals: (symbol: string) => ['companies', 'technicals', symbol] as const,
  },

  profile: ['profile'] as const,

  watchlist: { all: ['watchlist'] as const },

  plans: {
    all: ['plans'] as const,
    list: (filters: {
      status?: string | undefined;
      limit?: number | undefined;
      offset?: number | undefined;
    }) => ['plans', 'list', filters] as const,
    detail: (id: number) => ['plans', 'detail', id] as const,
  },

  portfolio: {
    all: ['portfolio'] as const,
    summary: ['portfolio', 'summary'] as const,
    trades: (limit: number) => ['portfolio', 'trades', limit] as const,
  },

  alerts: {
    all: ['alerts'] as const,
    list: (includeAcknowledged: boolean) => ['alerts', 'list', includeAcknowledged] as const,
  },
} as const;
