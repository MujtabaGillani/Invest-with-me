import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError, api, isApiError, request } from './apiClient';

/**
 * API client tests.
 *
 * This is the one place the backend's error envelope is parsed, so these tests pin
 * that parsing - including the paths that only happen when something is already
 * wrong: a proxy answering with HTML, a backend that is not running, an aborted
 * request. Those are exactly the paths that are never exercised by hand.
 */

function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

/**
 * Mock signatures mirror `fetch` exactly.
 *
 * Without the explicit parameter list, `vi.fn` infers a zero-argument mock and
 * `mock.calls[0]` types as an empty tuple - so assertions about the URL and the
 * request init would not typecheck.
 */
type FetchArgs = Parameters<typeof fetch>;

function mockFetch(response: Response) {
  const fetchMock = vi.fn((..._args: FetchArgs) => Promise.resolve(response));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** Separate from mockFetch: a rejection is a different code path, not a variant. */
function mockFetchRejection(cause: Error) {
  const fetchMock = vi.fn((..._args: FetchArgs) => Promise.reject(cause));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('request', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns the parsed body on success', async () => {
    mockFetch(jsonResponse({ symbol: 'LUCK' }));
    await expect(request<{ symbol: string }>('/companies/LUCK')).resolves.toEqual({
      symbol: 'LUCK',
    });
  });

  it('prefixes the configured base URL', async () => {
    const fetchMock = mockFetch(jsonResponse({}));
    await request('/companies');
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/companies');
  });

  it('drops empty query parameters instead of sending blanks', async () => {
    // Lets callers pass optional filters straight through.
    const fetchMock = mockFetch(jsonResponse({}));
    await request('/companies', {
      query: { search: 'luck', sector: undefined, limit: 25, offset: 0, blank: '' },
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/companies?search=luck&limit=25&offset=0');
  });

  it('serialises a body and sets the content type', async () => {
    const fetchMock = mockFetch(jsonResponse({}, 201));
    await api.post('/plans', { symbol: 'LUCK' });

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe('{"symbol":"LUCK"}');
    expect(init?.headers).toEqual({ 'Content-Type': 'application/json' });
  });

  it('sends no body or content type on a GET', async () => {
    const fetchMock = mockFetch(jsonResponse({}));
    await api.get('/companies');

    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
    expect(init?.headers).toBeUndefined();
  });

  it('returns null for 204, which the profile endpoint uses meaningfully', async () => {
    // 204 means "you have not written a profile yet" - a state, not an error.
    mockFetch(new Response(null, { status: 204 }));
    await expect(request<null>('/profile')).resolves.toBeNull();
  });
});

describe('error envelope parsing', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('maps the envelope onto an ApiError', async () => {
    mockFetch(
      jsonResponse(
        {
          error: {
            code: 'company_not_found',
            message: "No company found for symbol 'NOPE'.",
            details: { symbol: 'NOPE' },
            request_id: 'abc123',
          },
        },
        404,
      ),
    );

    const error = await request('/companies/NOPE').catch((caught: unknown) => caught);

    expect(isApiError(error)).toBe(true);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(404);
    expect(apiError.code).toBe('company_not_found');
    expect(apiError.message).toBe("No company found for symbol 'NOPE'.");
    expect(apiError.details).toEqual({ symbol: 'NOPE' });
    expect(apiError.requestId).toBe('abc123');
    expect(apiError.isNotFound).toBe(true);
  });

  it('exposes the flags callers branch on', async () => {
    mockFetch(
      jsonResponse(
        { error: { code: 'insufficient_data', message: 'No statements loaded.', details: {} } },
        422,
      ),
    );
    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;

    expect(error.isInsufficientData).toBe(true);
    expect(error.isBusinessRuleViolation).toBe(false);
    expect(error.isConflict).toBe(false);
  });

  it('extracts per-field errors from a validation failure', async () => {
    mockFetch(
      jsonResponse(
        {
          error: {
            code: 'request_validation_error',
            message: 'The request could not be processed as sent.',
            details: {
              errors: [
                { location: ['body', 'quantity'], message: 'must be greater than 0', type: 'gt' },
              ],
            },
          },
        },
        422,
      ),
    );

    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;

    expect(error.fieldErrors).toHaveLength(1);
    expect(error.fieldErrors[0]?.location).toEqual(['body', 'quantity']);
  });

  it('returns no field errors for a failure that is not a validation error', async () => {
    mockFetch(jsonResponse({ error: { code: 'conflict', message: 'Already exists.' } }, 409));
    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;

    expect(error.fieldErrors).toEqual([]);
    expect(error.isConflict).toBe(true);
  });

  it('extracts the reasons a plan cannot be committed', async () => {
    mockFetch(
      jsonResponse(
        {
          error: {
            code: 'validation_error',
            message: 'This plan is not ready to commit to.',
            details: { blocking_reasons: ['No stop-loss set.', 'Not yet answered: …'] },
          },
        },
        422,
      ),
    );

    const error = (await request('/x', { method: 'POST' }).catch(
      (caught: unknown) => caught,
    )) as ApiError;

    expect(error.blockingReasons).toEqual(['No stop-loss set.', 'Not yet answered: …']);
  });

  it('falls back to a readable message when the body is not the envelope', async () => {
    // What a reverse proxy or load balancer returns when the app never sees the
    // request. Must not surface as a JSON parse error.
    mockFetch(new Response('<html>502 Bad Gateway</html>', { status: 502 }));

    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;

    expect(error.code).toBe('http_502');
    expect(error.message).toContain('could not complete');
  });

  it('reads the request id from the response header when the body has none', async () => {
    mockFetch(new Response('nope', { status: 500, headers: { 'X-Request-ID': 'from-header' } }));
    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;
    expect(error.requestId).toBe('from-header');
  });

  it('presents a transport failure as an ApiError so callers need one error path', async () => {
    mockFetchRejection(new TypeError('Failed to fetch'));

    const error = (await request('/x').catch((caught: unknown) => caught)) as ApiError;

    expect(isApiError(error)).toBe(true);
    expect(error.code).toBe('network_error');
    expect(error.status).toBe(0);
    expect(error.message).toContain('Could not reach the server');
  });

  it('re-throws an abort untouched, because cancellation is not failure', async () => {
    // React Query distinguishes the two; wrapping this would break that.
    const abort = new Error('The operation was aborted.');
    abort.name = 'AbortError';
    mockFetchRejection(abort);

    const error = await request('/x').catch((caught: unknown) => caught);

    expect(isApiError(error)).toBe(false);
    expect((error as Error).name).toBe('AbortError');
  });
});

describe('isApiError', () => {
  it('narrows only genuine ApiErrors', () => {
    expect(isApiError(new ApiError({ status: 404, code: 'x', message: 'y' }))).toBe(true);
    expect(isApiError(new Error('plain'))).toBe(false);
    expect(isApiError('a string')).toBe(false);
    expect(isApiError(null)).toBe(false);
  });
});
