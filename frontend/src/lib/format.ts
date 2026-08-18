/**
 * Display formatting.
 *
 * One rule underpins this module: **money and percentages arrive from the API as
 * strings**, because the backend uses `Decimal` and serialises it as a string to
 * avoid float rounding. Parsing them to `number` purely for display is fine -
 * nothing here feeds back into a calculation - but it must be done deliberately,
 * in one place, and it must survive `null`.
 *
 * Every helper accepts `null | undefined` and returns a dash. "Not applicable"
 * and "zero" are different statements, and a UI that renders `0.00` for a metric
 * that could not be computed is lying.
 */

/** Shown wherever a value is absent. An em dash, not a zero. */
export const EMPTY = '—';

/** Numeric values from the API: `Decimal` fields arrive as strings. */
export type ApiNumber = string | number | null | undefined;

/**
 * Parse an API numeric into a `number`, or `null` when it is absent or unusable.
 *
 * A non-numeric string returns `null` rather than `NaN`, so a malformed payload
 * shows as "—" instead of leaking "NaN" into the interface.
 */
export function toNumber(value: ApiNumber): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Format a PKR amount.
 *
 * Large figures are abbreviated, using the units a Pakistani reader expects: a
 * revenue line reads "PKR 195.0bn", not "PKR 195,000,000,000". Position-level
 * amounts stay unabbreviated so they can be reconciled against a broker
 * statement.
 */
export function formatMoney(
  value: ApiNumber,
  options: { abbreviate?: boolean; decimals?: number } = {},
): string {
  const amount = toNumber(value);
  if (amount === null) return EMPTY;

  const { abbreviate = false, decimals = 2 } = options;

  if (abbreviate) {
    const magnitude = Math.abs(amount);
    const sign = amount < 0 ? '-' : '';
    if (magnitude >= 1e12) return `${sign}PKR ${(magnitude / 1e12).toFixed(2)}tn`;
    if (magnitude >= 1e9) return `${sign}PKR ${(magnitude / 1e9).toFixed(2)}bn`;
    if (magnitude >= 1e6) return `${sign}PKR ${(magnitude / 1e6).toFixed(2)}m`;
    if (magnitude >= 1e3) return `${sign}PKR ${(magnitude / 1e3).toFixed(1)}k`;
  }

  return `PKR ${amount.toLocaleString('en-PK', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** Format a share count. Whole numbers stay whole - PSX has no fractional shares. */
export function formatQuantity(value: ApiNumber): string {
  const quantity = toNumber(value);
  if (quantity === null) return EMPTY;
  return quantity.toLocaleString('en-PK', {
    minimumFractionDigits: 0,
    maximumFractionDigits: Number.isInteger(quantity) ? 0 : 4,
  });
}

/**
 * Format a percentage.
 *
 * @param signed - prefix a `+` on positive values. Used for changes, where the
 *   direction is the point; omitted for weights, where a `+` would be noise.
 */
export function formatPercent(
  value: ApiNumber,
  options: { decimals?: number; signed?: boolean } = {},
): string {
  const percent = toNumber(value);
  if (percent === null) return EMPTY;

  const { decimals = 2, signed = false } = options;
  const sign = signed && percent > 0 ? '+' : '';
  return `${sign}${percent.toFixed(decimals)}%`;
}

/** Format a multiple, e.g. a P/E ratio or a gearing figure. */
export function formatMultiple(value: ApiNumber, decimals = 2): string {
  const multiple = toNumber(value);
  if (multiple === null) return EMPTY;
  return `${multiple.toFixed(decimals)}x`;
}

/**
 * Format any of the units the analysis engines emit.
 *
 * The API tags each metric with its own unit (`'%'`, `'x'`, `'PKR'`, or null for
 * a bare count), so the UI renders whatever the server computed without a table
 * of per-metric special cases.
 */
export function formatMetricValue(value: ApiNumber, unit: string | null | undefined): string {
  if (toNumber(value) === null) return EMPTY;
  switch (unit) {
    case '%':
      return formatPercent(value);
    case 'x':
      return formatMultiple(value);
    case 'PKR':
      // Financial-statement figures are large; per-share figures are not. The
      // threshold picks the right presentation without the caller deciding.
      return formatMoney(value, { abbreviate: Math.abs(toNumber(value) ?? 0) >= 1e6 });
    default:
      return (toNumber(value) ?? 0).toLocaleString('en-PK', { maximumFractionDigits: 2 });
  }
}

/** Format an ISO date (`2025-06-30`) as `30 Jun 2025`. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** Format an ISO timestamp as `30 Jun 2025, 14:05`. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return EMPTY;
  return `${formatDate(value)}, ${date.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  })}`;
}

/**
 * Describe how long ago something happened, in the terms the review-due rule
 * uses ("It has been 120 days since you last reviewed this").
 */
export function formatRelativeDays(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const then = new Date(value);
  if (Number.isNaN(then.getTime())) return EMPTY;

  const days = Math.floor((Date.now() - then.getTime()) / 86_400_000);
  if (days < 0) return 'in the future';
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 30) return `${days} days ago`;
  if (days < 365) {
    const months = Math.floor(days / 30);
    return months === 1 ? 'a month ago' : `${months} months ago`;
  }
  const years = Math.floor(days / 365);
  return years === 1 ? 'a year ago' : `${years} years ago`;
}

/**
 * Sign of a value, for colouring gains and losses.
 *
 * Returns `'neutral'` for both zero and absent, because a missing value must not
 * be coloured as though it were a result.
 */
export function signOf(value: ApiNumber): 'positive' | 'negative' | 'neutral' {
  const parsed = toNumber(value);
  if (parsed === null || parsed === 0) return 'neutral';
  return parsed > 0 ? 'positive' : 'negative';
}

/** Convert an enum value (`commercial_banks`) to a label, as a last resort. */
export function humanise(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const spaced = value.replace(/_/g, ' ');
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
