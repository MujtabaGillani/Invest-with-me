import { describe, expect, it } from 'vitest';

import {
  EMPTY,
  formatDate,
  formatMetricValue,
  formatMoney,
  formatMultiple,
  formatPercent,
  formatQuantity,
  formatRelativeDays,
  humanise,
  signOf,
  toNumber,
} from './format';

/**
 * Formatter tests.
 *
 * The emphasis is on absent values. Money and percentages arrive from the API as
 * strings, and a missing one means "could not be computed" - rendering it as
 * `0.00` would state a result that does not exist. Every helper is checked for
 * that, because it is the failure that would quietly mislead.
 */

describe('toNumber', () => {
  it('parses the strings the API sends for Decimal fields', () => {
    expect(toNumber('123.45')).toBe(123.45);
    expect(toNumber('-0.5')).toBe(-0.5);
  });

  it('passes numbers through', () => {
    expect(toNumber(42)).toBe(42);
  });

  it('treats absent values as absent, not zero', () => {
    expect(toNumber(null)).toBeNull();
    expect(toNumber(undefined)).toBeNull();
    expect(toNumber('')).toBeNull();
  });

  it('rejects a non-numeric string rather than returning NaN', () => {
    // NaN would leak into the interface as the literal text "NaN".
    expect(toNumber('not a number')).toBeNull();
  });

  it('rejects infinities', () => {
    expect(toNumber('Infinity')).toBeNull();
  });
});

describe('formatMoney', () => {
  it('formats with a currency prefix and thousands separators', () => {
    expect(formatMoney('1234.5')).toBe('PKR 1,234.50');
  });

  it('renders a dash for an absent amount', () => {
    expect(formatMoney(null)).toBe(EMPTY);
    expect(formatMoney(undefined)).toBe(EMPTY);
  });

  it('renders zero as zero', () => {
    // Distinct from absent: a zero balance is a fact.
    expect(formatMoney('0')).toBe('PKR 0.00');
  });

  it('abbreviates large figures using units a reader expects', () => {
    expect(formatMoney('195000000000', { abbreviate: true })).toBe('PKR 195.00bn');
    expect(formatMoney('4200000', { abbreviate: true })).toBe('PKR 4.20m');
    expect(formatMoney('45000', { abbreviate: true })).toBe('PKR 45.0k');
  });

  it('keeps the sign when abbreviating a negative figure', () => {
    expect(formatMoney('-3500000', { abbreviate: true })).toBe('-PKR 3.50m');
  });

  it('does not abbreviate below a thousand', () => {
    expect(formatMoney('892', { abbreviate: true })).toBe('PKR 892.00');
  });

  it('honours a requested precision', () => {
    expect(formatMoney('12.3456', { decimals: 4 })).toBe('PKR 12.3456');
  });
});

describe('formatQuantity', () => {
  it('renders a whole share count without decimals', () => {
    expect(formatQuantity('250')).toBe('250');
  });

  it('keeps fractional precision when there is any', () => {
    expect(formatQuantity('250.5')).toBe('250.5');
  });

  it('renders a dash for an absent count', () => {
    expect(formatQuantity(null)).toBe(EMPTY);
  });
});

describe('formatPercent', () => {
  it('appends a percent sign', () => {
    expect(formatPercent('11.15')).toBe('11.15%');
  });

  it('signs a positive change only when asked', () => {
    expect(formatPercent('11.15', { signed: true })).toBe('+11.15%');
    expect(formatPercent('11.15')).toBe('11.15%');
  });

  it('always shows a negative sign', () => {
    expect(formatPercent('-8.2')).toBe('-8.20%');
  });

  it('does not sign zero', () => {
    expect(formatPercent('0', { signed: true })).toBe('0.00%');
  });

  it('renders a dash for an absent value', () => {
    expect(formatPercent(null)).toBe(EMPTY);
  });
});

describe('formatMultiple', () => {
  it('appends an x', () => {
    expect(formatMultiple('12.5')).toBe('12.50x');
  });

  it('renders a dash for an absent ratio', () => {
    // A loss-making company has no P/E, and it must not read as "0.00x".
    expect(formatMultiple(null)).toBe(EMPTY);
  });
});

describe('formatMetricValue', () => {
  it('renders each unit the analysis engines emit', () => {
    expect(formatMetricValue('15.02', '%')).toBe('15.02%');
    expect(formatMetricValue('10.0', 'x')).toBe('10.00x');
    expect(formatMetricValue('14.0', 'PKR')).toBe('PKR 14.00');
    expect(formatMetricValue('3', null)).toBe('3');
  });

  it('abbreviates a statement-scale PKR figure but not a per-share one', () => {
    expect(formatMetricValue('192500000', 'PKR')).toBe('PKR 192.50m');
    expect(formatMetricValue('14.0', 'PKR')).toBe('PKR 14.00');
  });

  it('renders a dash whatever the unit when the value is absent', () => {
    for (const unit of ['%', 'x', 'PKR', null]) {
      expect(formatMetricValue(null, unit)).toBe(EMPTY);
    }
  });
});

describe('formatDate', () => {
  it('formats an ISO date readably', () => {
    expect(formatDate('2025-06-30')).toBe('30 Jun 2025');
  });

  it('renders a dash for absent or unparseable input', () => {
    expect(formatDate(null)).toBe(EMPTY);
    expect(formatDate('not a date')).toBe(EMPTY);
  });
});

describe('formatRelativeDays', () => {
  const daysAgo = (days: number) => new Date(Date.now() - days * 86_400_000).toISOString();

  it('describes recent and distant timestamps', () => {
    expect(formatRelativeDays(daysAgo(0))).toBe('today');
    expect(formatRelativeDays(daysAgo(1))).toBe('yesterday');
    expect(formatRelativeDays(daysAgo(12))).toBe('12 days ago');
    expect(formatRelativeDays(daysAgo(45))).toBe('a month ago');
    expect(formatRelativeDays(daysAgo(120))).toBe('4 months ago');
    expect(formatRelativeDays(daysAgo(400))).toBe('a year ago');
  });

  it('does not claim a future timestamp is in the past', () => {
    expect(formatRelativeDays(daysAgo(-5))).toBe('in the future');
  });

  it('renders a dash for absent input', () => {
    expect(formatRelativeDays(null)).toBe(EMPTY);
  });
});

describe('signOf', () => {
  it('classifies gains and losses', () => {
    expect(signOf('120')).toBe('positive');
    expect(signOf('-120')).toBe('negative');
  });

  it('treats zero and absent as neutral', () => {
    // An absent value must never be coloured as though it were a result.
    expect(signOf('0')).toBe('neutral');
    expect(signOf(null)).toBe('neutral');
  });
});

describe('humanise', () => {
  it('turns an enum value into a label', () => {
    expect(humanise('commercial_banks')).toBe('Commercial banks');
    expect(humanise('uptrend')).toBe('Uptrend');
  });

  it('renders a dash for absent input', () => {
    expect(humanise(null)).toBe(EMPTY);
  });
});
