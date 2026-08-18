import { toNumber, type ApiNumber } from '@/lib/format';

/**
 * Inline SVG trend charts.
 *
 * Hand-rolled rather than pulled from a charting library. The requirement is three
 * shapes - a five-point sparkline next to a metric, a single price line, and an
 * invested-versus-value pair - with no axes, legends, tooltips or interaction. A
 * charting dependency would add roughly 100kB and a version to keep current in
 * exchange for features this application does not use. If richer charts are ever
 * needed, that is the moment to add one, not before.
 *
 * Both components are decorative: they carry `aria-hidden` and the figures they
 * illustrate are always present as text nearby, so nothing is conveyed by the
 * graphic alone.
 */

/** Build an SVG polyline path from a series, scaled to the viewbox. */
function buildPath(values: number[], width: number, height: number, padding: number): string {
  if (values.length < 2) return '';

  const min = Math.min(...values);
  const max = Math.max(...values);
  // A flat series would divide by zero; draw it down the middle instead.
  const range = max - min || 1;
  const usableHeight = height - padding * 2;
  const step = (width - padding * 2) / (values.length - 1);

  return values
    .map((value, index) => {
      const x = padding + index * step;
      // SVG y grows downward, so the ratio is inverted.
      const y = padding + usableHeight - ((value - min) / range) * usableHeight;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

interface SparklineProps {
  /** Oldest first. Nulls are dropped, so a partial history still draws. */
  values: ApiNumber[];
  width?: number | undefined;
  height?: number | undefined;
  className?: string | undefined;
}

/**
 * A small trend line for a metric's per-year history.
 *
 * Coloured by direction - up is not "good", it is just up. A rising debt-to-equity
 * line is drawn in the same colour as rising revenue, because whether that is
 * welcome is what the verdict badge next to it is for.
 */
export function Sparkline({ values, width = 72, height = 24, className }: SparklineProps) {
  const series = values.map(toNumber).filter((value): value is number => value !== null);
  if (series.length < 2) return null;

  const path = buildPath(series, width, height, 2);
  const first = series[0] ?? 0;
  const last = series[series.length - 1] ?? 0;
  const stroke = last >= first ? 'var(--color-verdict-adequate)' : 'var(--color-ink-subtle)';

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      width={width}
      height={height}
      aria-hidden="true"
      className={className}
      role="presentation"
    >
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinecap="round" />
    </svg>
  );
}

interface PriceChartProps {
  /** Closing prices, oldest first. */
  closes: ApiNumber[];
  height?: number | undefined;
  className?: string | undefined;
}

/**
 * A full-width price line with a soft fill.
 *
 * Uses a `viewBox` with `preserveAspectRatio="none"` so it stretches to whatever
 * width the container has, without needing a resize observer.
 */
export function PriceChart({ closes, height = 120, className }: PriceChartProps) {
  const series = closes.map(toNumber).filter((value): value is number => value !== null);
  if (series.length < 2) return null;

  const width = 600;
  const padding = 4;
  const path = buildPath(series, width, height, padding);
  const first = series[0] ?? 0;
  const last = series[series.length - 1] ?? 0;
  const rising = last >= first;
  const stroke = rising ? 'var(--color-gain)' : 'var(--color-loss)';

  // Close the path down to the baseline to shade the area under the line.
  const areaPath = `${path} L${width - padding},${height} L${padding},${height} Z`;
  const gradientId = rising ? 'price-area-rising' : 'price-area-falling';

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      role="presentation"
      className={className}
      style={{ width: '100%', height }}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.18} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** Build a path over an explicit domain, so several series share one scale. */
function buildScaledPath(
  values: number[],
  min: number,
  max: number,
  width: number,
  height: number,
  padding: number,
): string {
  if (values.length < 2) return '';
  const range = max - min || 1;
  const usableHeight = height - padding * 2;
  const step = (width - padding * 2) / (values.length - 1);
  return values
    .map((value, index) => {
      const x = padding + index * step;
      const y = padding + usableHeight - ((value - min) / range) * usableHeight;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

interface ProfitChartProps {
  /** Cost basis on each date, oldest first. */
  invested: ApiNumber[];
  /** Market value on the same dates, in the same order. */
  marketValue: ApiNumber[];
  height?: number | undefined;
  className?: string | undefined;
}

/**
 * Invested versus market value, with the gap between them shaded.
 *
 * The gap *is* the profit or loss, which is why this is two lines rather than a
 * single profit line: a single line hides whether a rising number came from the
 * holdings gaining value or from simply putting more money in. Both series share
 * one vertical scale for the same reason - independently scaled axes would make a
 * small gap look enormous.
 *
 * The shading is green above the invested line and red below it. That is the one
 * place in this app where colour carries a judgement, and it is safe here because
 * "worth less than I paid" is a fact rather than an opinion. It is also not the
 * only cue: the figures are always printed as text beside the chart, and the chart
 * itself is `aria-hidden`.
 */
export function ProfitChart({ invested, marketValue, height = 160, className }: ProfitChartProps) {
  const costs = invested.map(toNumber);
  const values = marketValue.map(toNumber);
  // Only dates where both series are known can be compared, so a null in either
  // drops the pair rather than shifting one line relative to the other.
  const pairs = costs
    .map((cost, index) => [cost, values[index] ?? null] as const)
    .filter((pair): pair is readonly [number, number] => pair[0] !== null && pair[1] !== null);
  if (pairs.length < 2) return null;

  const costSeries = pairs.map(([cost]) => cost);
  const valueSeries = pairs.map(([, value]) => value);

  const width = 600;
  const padding = 4;
  // A shared domain, padded slightly so neither line sits on the frame.
  const rawMin = Math.min(...costSeries, ...valueSeries);
  const rawMax = Math.max(...costSeries, ...valueSeries);
  const headroom = (rawMax - rawMin || Math.abs(rawMax) || 1) * 0.08;
  const min = rawMin - headroom;
  const max = rawMax + headroom;

  const costPath = buildScaledPath(costSeries, min, max, width, height, padding);
  const valuePath = buildScaledPath(valueSeries, min, max, width, height, padding);

  const lastCost = costSeries[costSeries.length - 1] ?? 0;
  const lastValue = valueSeries[valueSeries.length - 1] ?? 0;
  const inProfit = lastValue >= lastCost;
  const stroke = inProfit ? 'var(--color-gain)' : 'var(--color-loss)';

  // Close the value line back along the reversed cost line to shade the gap.
  const reversedCost = buildScaledPath(
    [...costSeries].reverse(),
    min,
    max,
    width,
    height,
    padding,
  ).replace(/^M/, 'L');
  const gapPath = `${valuePath} ${reversedCost} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      role="presentation"
      className={className}
      style={{ width: '100%', height }}
    >
      <path d={gapPath} fill={stroke} fillOpacity={0.14} stroke="none" />
      <path
        d={costPath}
        fill="none"
        stroke="var(--color-ink-subtle)"
        strokeWidth={1}
        strokeDasharray="4 3"
        vectorEffect="non-scaling-stroke"
      />
      <path
        d={valuePath}
        fill="none"
        stroke={stroke}
        strokeWidth={1.75}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
