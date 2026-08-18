import { toNumber, type ApiNumber } from '@/lib/format';

/**
 * Inline SVG trend charts.
 *
 * Hand-rolled rather than pulled from a charting library. The requirement is two
 * shapes - a five-point sparkline next to a metric, and a single price line - with
 * no axes, legends, tooltips or interaction. A charting dependency would add
 * roughly 100kB and a version to keep current in exchange for features this
 * application does not use. If richer charts are ever needed, that is the moment
 * to add one, not before.
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
