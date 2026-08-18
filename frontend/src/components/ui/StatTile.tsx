import clsx from 'clsx';
import type { ReactNode } from 'react';

import { signOf, type ApiNumber } from '@/lib/format';

/**
 * A single headline figure.
 *
 * `tone` supports `'signed'`, which colours the value green or red from its own
 * sign. That is used only for money outcomes - a profit or loss. It is
 * deliberately *not* used for metric verdicts: those get a
 * {@link import('./Badge').VerdictBadge}, because colouring a P/E ratio green
 * would read as "buy" rather than "meets the criterion".
 */

interface StatTileProps {
  label: string;
  value: ReactNode;
  /** Small text under the value: a comparison, a date, a count. */
  detail?: ReactNode | undefined;
  /** `'signed'` colours from `signedFrom`; the others are fixed. */
  tone?: 'default' | 'signed' | 'muted' | undefined;
  /** The raw number whose sign drives the colour when `tone` is `'signed'`. */
  signedFrom?: ApiNumber;
  className?: string | undefined;
}

export function StatTile({
  label,
  value,
  detail,
  tone = 'default',
  signedFrom,
  className,
}: StatTileProps) {
  const sign = tone === 'signed' ? signOf(signedFrom) : 'neutral';

  return (
    <div className={clsx('bg-surface-raised border-border rounded-lg border px-4 py-3', className)}>
      <p className="text-ink-muted text-xs font-medium tracking-wide uppercase">{label}</p>
      <p
        className={clsx(
          'numeric mt-1.5 text-xl font-semibold',
          tone === 'muted' && 'text-ink-muted',
          sign === 'positive' && 'text-gain',
          sign === 'negative' && 'text-loss',
          (tone === 'default' || sign === 'neutral') && tone !== 'muted' && 'text-ink',
        )}
      >
        {value}
      </p>
      {detail ? <p className="text-ink-subtle mt-1 text-xs">{detail}</p> : null}
    </div>
  );
}

/** A responsive row of tiles. */
export function StatRow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string | undefined;
}) {
  return (
    <div className={clsx('grid gap-3 sm:grid-cols-2 lg:grid-cols-4', className)}>{children}</div>
  );
}
