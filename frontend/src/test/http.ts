import { vi } from 'vitest';

/**
 * URL-routed `fetch` stub for component tests.
 *
 * Component tests need several endpoints answered at once - a form usually needs
 * `/meta` for its dropdowns as well as the endpoint it submits to - so a single
 * blanket mock is not enough.
 *
 * Deliberately stubs `fetch` rather than mocking the query hooks. Mocking the hooks
 * would skip `apiClient`, and the error-envelope parsing is exactly the behaviour
 * these tests need to exercise: a component's job is to render what the server
 * actually said.
 */

export interface StubRoute {
  /** Substring matched against the request URL. First match wins. */
  match: string;
  status?: number;
  /** Serialised as the JSON body. Omit for a 204. */
  body?: unknown;
}

export interface FetchStub {
  /** Every request made, in order. */
  calls: { url: string; method: string; body: unknown }[];
  /** Requests to URLs containing `fragment`. */
  callsTo: (fragment: string) => { url: string; method: string; body: unknown }[];
}

/**
 * Install a `fetch` stub that answers from `routes`.
 *
 * An unmatched URL rejects loudly rather than returning an empty 200 - a silent
 * empty response would make a test fail somewhere far from the missing route.
 */
export function stubFetch(routes: StubRoute[]): FetchStub {
  const calls: FetchStub['calls'] = [];

  const fetchMock = vi.fn((...args: Parameters<typeof fetch>) => {
    const [input, init] = args;
    // `fetch` accepts a string, a URL or a Request. Narrowed explicitly rather
    // than calling toString() on the union, which would stringify a Request as
    // "[object Object]" and make every route match fail confusingly.
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
    const method = init?.method ?? 'GET';
    const rawBody = init?.body;

    calls.push({
      url,
      method,
      body: typeof rawBody === 'string' ? JSON.parse(rawBody) : undefined,
    });

    const route = routes.find((candidate) => url.includes(candidate.match));
    if (!route) {
      return Promise.reject(new Error(`No stub route matches ${method} ${url}`));
    }

    const status = route.status ?? 200;
    if (status === 204 || route.body === undefined) {
      return Promise.resolve(new Response(null, { status }));
    }
    return Promise.resolve(
      new Response(JSON.stringify(route.body), {
        status,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });

  vi.stubGlobal('fetch', fetchMock);

  return {
    calls,
    callsTo: (fragment: string) => calls.filter((call) => call.url.includes(fragment)),
  };
}

/** The backend's error envelope, for stubbing a failure response. */
export function errorEnvelope(
  code: string,
  message: string,
  details: Record<string, unknown> = {},
) {
  return { error: { code, message, details, request_id: 'test-request-id' } };
}

/** A minimal `/meta` response - enough to populate the dropdowns a form renders. */
export const META_RESPONSE = {
  provider: {
    name: 'seeded',
    description: 'Illustrative, generated dataset.',
    is_synthetic: true,
    verification_sources: ['PSX filings (PUCARS) - https://dps.psx.com.pk/'],
  },
  sectors: [
    { value: 'cement', label: 'Cement', description: null },
    { value: 'commercial_banks', label: 'Commercial Banks', description: null },
  ],
  time_horizons: [
    { value: 'short_term', label: 'Short term (under a year)', description: 'Closer to trading.' },
    { value: 'long_term', label: 'Long term (3-5+ years)', description: 'The intended horizon.' },
  ],
  risk_tolerances: [
    { value: 'moderate', label: 'Moderate', description: 'Comfortable with volatility.' },
    { value: 'aggressive', label: 'Aggressive', description: 'Willing to accept large swings.' },
  ],
  metric_verdicts: [{ value: 'strong', label: 'Strong', description: null }],
  prebuy_checklist: [{ value: 'understands_business', label: 'Do I understand it?' }],
  disclaimer: { is_financial_advice: false, text: 'Educational and general in nature.' },
};
