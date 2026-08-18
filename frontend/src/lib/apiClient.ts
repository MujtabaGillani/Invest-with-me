/**
 * The single HTTP entry point.
 *
 * Nothing in the app calls `fetch` directly. Everything goes through
 * {@link request}, which means the error envelope is parsed in exactly one place
 * and every caller can rely on getting either a typed body or an
 * {@link ApiError} carrying the server's stable `code`.
 */

/** Base URL for the API. Defaults to the Vite dev proxy path. */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

/**
 * The backend's error envelope. Every failure has this shape - domain rule,
 * request validation, unmatched route, or unhandled bug. See
 * `backend/app/core/errors.py`.
 */
interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    request_id?: string | null;
  };
}

/** One entry from a request-validation failure's `details.errors`. */
export interface FieldError {
  location: (string | number)[];
  message: string;
  type: string;
}

/**
 * A failed API call.
 *
 * Carries the server's `code` so callers can branch on the failure rather than
 * matching on prose, and the `requestId` so a user reporting a problem can quote
 * something that appears in the server logs.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(init: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, unknown>;
    requestId?: string | null;
  }) {
    super(init.message);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.details = init.details ?? {};
    this.requestId = init.requestId ?? null;
  }

  /** True when the resource does not exist. */
  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** True when the request conflicts with the resource's current state. */
  get isConflict(): boolean {
    return this.status === 409;
  }

  /**
   * True when the request was well-formed but the data cannot support the
   * operation - for example a company with no filings loaded. Distinct from a
   * malformed payload, which the backend codes separately.
   */
  get isInsufficientData(): boolean {
    return this.code === 'insufficient_data';
  }

  /** True when a business rule was violated, e.g. selling more than is held. */
  get isBusinessRuleViolation(): boolean {
    return this.code === 'validation_error';
  }

  /**
   * Per-field validation errors, when the failure was a malformed payload.
   * Empty for every other kind of failure.
   */
  get fieldErrors(): FieldError[] {
    if (this.code !== 'request_validation_error') return [];
    const errors = this.details.errors;
    return Array.isArray(errors) ? (errors as FieldError[]) : [];
  }

  /**
   * Reasons a trade plan cannot be committed, when that is why the call failed.
   * The backend returns these as a list so the UI can show exactly what is
   * missing rather than a single unhelpful message.
   */
  get blockingReasons(): string[] {
    const reasons = this.details.blocking_reasons;
    return Array.isArray(reasons) ? (reasons as string[]) : [];
  }
}

/** Narrowing guard for `unknown` errors caught in components and hooks. */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';
  /** Serialised as JSON. Omit for GET and DELETE. */
  body?: unknown;
  /** Appended as a query string; `undefined` and `null` entries are dropped. */
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${API_BASE_URL}${path}`;
  if (!query) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    // Dropping empty values here means callers can pass optional filters
    // straight through without assembling the string themselves.
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  const queryString = params.toString();
  return queryString ? `${url}?${queryString}` : url;
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const { error } = value;
  return typeof error === 'object' && error !== null && 'code' in error && 'message' in error;
}

/**
 * Turn a non-2xx response into an {@link ApiError}.
 *
 * Falls back to a generic message when the body is not the expected envelope -
 * which happens when a proxy or load balancer answers instead of the
 * application, and must not surface as a confusing JSON parse error.
 */
async function toApiError(response: Response): Promise<ApiError> {
  const requestId = response.headers.get('X-Request-ID');

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }

  if (isErrorEnvelope(payload)) {
    return new ApiError({
      status: response.status,
      code: payload.error.code,
      message: payload.error.message,
      details: payload.error.details ?? {},
      requestId: payload.error.request_id ?? requestId,
    });
  }

  return new ApiError({
    status: response.status,
    code: `http_${response.status}`,
    message:
      response.status >= 500
        ? 'The server could not complete this request. Please try again.'
        : `Request failed with status ${response.status}.`,
    requestId,
  });
}

/**
 * Perform an API request.
 *
 * @typeParam T - the expected response body. Callers pass a type from
 *   `@/types`, which is generated from the backend's own schema.
 * @throws {ApiError} for any non-2xx response, and for a network failure - so a
 *   caller only ever has to handle one error type.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = options;

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      // Spread rather than assigning `undefined`: with exactOptionalPropertyTypes
      // an explicit undefined is not the same as an absent property, and
      // RequestInit does not accept the former.
      ...(body === undefined
        ? {}
        : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }),
      ...(signal ? { signal } : {}),
    });
  } catch (cause) {
    // A dropped connection or a backend that is not running. Presented as an
    // ApiError so callers do not need a second error path for transport
    // failures. An aborted request is re-thrown untouched, because React Query
    // treats cancellation differently from failure.
    // Checked by name rather than `instanceof DOMException`: DOMException is not
    // reliably an Error subclass across runtimes, so an instanceof test can miss a
    // genuine abort and wrap it as a network failure - which React Query would
    // then treat as an error rather than a cancellation.
    if (cause instanceof Error && cause.name === 'AbortError') throw cause;
    throw new ApiError({
      status: 0,
      code: 'network_error',
      message: 'Could not reach the server. Check that the API is running.',
    });
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  // 204 No Content is a real answer, not an empty body to parse: the profile
  // endpoint uses it to mean "you have not written one yet".
  if (response.status === 204) {
    return null as T;
  }

  return (await response.json()) as T;
}

/** Convenience wrappers. They exist only to keep call sites terse. */
export const api = {
  get: <T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal) =>
    request<T>(path, { method: 'GET', ...(query ? { query } : {}), ...(signal ? { signal } : {}) }),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: 'POST', body }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};
