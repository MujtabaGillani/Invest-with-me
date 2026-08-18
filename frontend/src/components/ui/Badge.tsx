import clsx from 'clsx';
import type { ReactNode } from 'react';

import type { AlertSeverity, MetricVerdict, TradePlanStatus } from '@/types';

/**
 * Status badges.
 *
 * The label text lives here rather than being passed in, so a verdict reads
 * identically on every screen. Note what the labels are *not*: `weak` renders as
 * "Weak", never "Sell", and `insufficient_data` renders as "Not enough data",
 * never "Poor" - the API's distinction between "fails the criterion" and "cannot
 * be judged" has to survive all the way to the pixel.
 */

interface BadgeProps {
  children: ReactNode;
  className?: string | undefined;
  title?: string | undefined;
}

function BaseBadge({ children, className, title }: BadgeProps) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap',
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Badge({ children, className, title }: BadgeProps) {
  return (
    <BaseBadge title={title} className={clsx('bg-surface-sunken text-ink-muted', className)}>
      {children}
    </BaseBadge>
  );
}

const VERDICT_PRESENTATION: Record<MetricVerdict, { label: string; className: string }> = {
  strong: {
    label: 'Strong',
    className: 'bg-verdict-strong-bg text-verdict-strong',
  },
  adequate: {
    label: 'Adequate',
    className: 'bg-verdict-adequate-bg text-verdict-adequate',
  },
  weak: {
    label: 'Weak',
    className: 'bg-verdict-weak-bg text-verdict-weak',
  },
  insufficient_data: {
    label: 'Not enough data',
    className: 'bg-verdict-unknown-bg text-verdict-unknown',
  },
};

export function VerdictBadge({ verdict }: { verdict: MetricVerdict }) {
  const { label, className } = VERDICT_PRESENTATION[verdict];
  return (
    <BaseBadge
      className={className}
      title={
        verdict === 'insufficient_data'
          ? 'The figures cannot support a judgement. This is not the same as a bad result.'
          : undefined
      }
    >
      {label}
    </BaseBadge>
  );
}

const SEVERITY_PRESENTATION: Record<AlertSeverity, { label: string; className: string }> = {
  info: { label: 'For information', className: 'bg-verdict-adequate-bg text-severity-info' },
  warning: { label: 'Worth a look', className: 'bg-verdict-weak-bg text-severity-warning' },
  critical: { label: 'Needs attention', className: 'bg-verdict-weak-bg text-severity-critical' },
};

export function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const { label, className } = SEVERITY_PRESENTATION[severity];
  return <BaseBadge className={className}>{label}</BaseBadge>;
}

const PLAN_STATUS_PRESENTATION: Record<
  TradePlanStatus,
  { label: string; className: string; title: string }
> = {
  draft: {
    label: 'Draft',
    className: 'bg-verdict-unknown-bg text-ink-muted',
    title: 'Still being worked through; not yet committed to.',
  },
  ready: {
    label: 'Committed',
    className: 'bg-accent-subtle text-accent',
    title: 'Checklist complete and exit rules set, but not yet acted on.',
  },
  executed: {
    label: 'Executed',
    className: 'bg-verdict-strong-bg text-verdict-strong',
    title: 'Bought. The profit target and stop-loss now govern a real position.',
  },
  abandoned: {
    label: 'Abandoned',
    className: 'bg-verdict-unknown-bg text-ink-subtle',
    title: 'Decided against buying. Kept as part of the decision journal.',
  },
  closed: {
    label: 'Closed',
    className: 'bg-verdict-unknown-bg text-ink-subtle',
    title: 'The position this plan governed has been exited.',
  },
};

export function PlanStatusBadge({ status }: { status: TradePlanStatus }) {
  const { label, className, title } = PLAN_STATUS_PRESENTATION[status];
  return (
    <BaseBadge className={className} title={title}>
      {label}
    </BaseBadge>
  );
}

/** A yes / no / unanswered marker for the pre-buy checklist. */
export function AnswerBadge({ answer }: { answer: boolean | null | undefined }) {
  if (answer === true) {
    return <BaseBadge className="bg-verdict-strong-bg text-verdict-strong">Yes</BaseBadge>;
  }
  if (answer === false) {
    return <BaseBadge className="bg-verdict-weak-bg text-verdict-weak">No</BaseBadge>;
  }
  return (
    <BaseBadge
      className="bg-verdict-unknown-bg text-ink-subtle"
      title="Not yet answered - which is different from answering no."
    >
      Unanswered
    </BaseBadge>
  );
}
