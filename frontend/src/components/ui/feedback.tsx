import clsx from 'clsx';
import type { ReactNode } from 'react';

import { isApiError } from '@/lib/apiClient';

import { Button } from './Button';

/**
 * Loading, empty and error states.
 *
 * These are components rather than inline JSX because they are the states a
 * reviewer is most likely to find missing. Every screen that fetches has three
 * outcomes, and having a named component for each makes it obvious when one has
 * been skipped.
 */

function Spinner({ className }: { className?: string | undefined }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={clsx(
        'border-ink-subtle inline-block size-4 animate-spin rounded-full border-2 border-t-transparent',
        className,
      )}
    />
  );
}

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="text-ink-muted flex items-center justify-center gap-3 py-12 text-sm">
      <Spinner />
      <span>{label}</span>
    </div>
  );
}

/** Skeleton rows, for tables where the shape is known before the data arrives. */
export function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <div className="animate-pulse space-y-2 p-5" aria-hidden="true">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div key={rowIndex} className="flex gap-3">
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <div key={columnIndex} className="bg-surface-sunken h-4 flex-1 rounded" />
          ))}
        </div>
      ))}
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  /** What this screen is for, and what to do first. */
  description?: ReactNode | undefined;
  action?: ReactNode | undefined;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="px-5 py-12 text-center">
      <p className="text-ink text-sm font-medium">{title}</p>
      {description ? (
        <p className="text-ink-muted mx-auto mt-1.5 max-w-md text-sm">{description}</p>
      ) : null}
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

interface ErrorStateProps {
  error: unknown;
  /** Rendered as a retry button when supplied. */
  onRetry?: (() => void) | undefined;
  /** Overrides the message. Use when the generic one would confuse. */
  title?: string | undefined;
}

/**
 * Present a failed request.
 *
 * Shows the server's own message, which is written to be read by a user, plus the
 * request id when there is one - so a bug report can quote something that appears
 * in the server logs.
 */
export function ErrorState({ error, onRetry, title }: ErrorStateProps) {
  const message = isApiError(error)
    ? error.message
    : error instanceof Error
      ? error.message
      : 'Something went wrong.';
  const requestId = isApiError(error) ? error.requestId : null;

  return (
    <div
      role="alert"
      className="border-verdict-weak/30 bg-verdict-weak-bg mx-5 my-5 rounded-md border px-4 py-3"
    >
      <p className="text-verdict-weak text-sm font-medium">{title ?? 'Could not load this'}</p>
      <p className="text-ink mt-1 text-sm">{message}</p>
      {requestId ? (
        <p className="text-ink-subtle numeric mt-1.5 text-xs">Reference: {requestId}</p>
      ) : null}
      {onRetry ? (
        <div className="mt-3">
          <Button size="sm" onClick={onRetry}>
            Try again
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/**
 * An inline notice.
 *
 * `tone` is descriptive, never prescriptive: "note" and "caution" rather than
 * "success" and "danger", because nothing this app tells the user is a verdict on
 * whether they did the right thing.
 */
export function Notice({
  tone = 'note',
  title,
  children,
}: {
  tone?: 'note' | 'caution' | 'positive' | undefined;
  title?: ReactNode | undefined;
  children: ReactNode;
}) {
  const toneClasses = {
    note: 'border-border bg-surface-sunken text-ink',
    caution: 'border-verdict-weak/30 bg-verdict-weak-bg text-ink',
    positive: 'border-verdict-strong/30 bg-verdict-strong-bg text-ink',
  }[tone];

  return (
    <div className={clsx('rounded-md border px-4 py-3 text-sm', toneClasses)}>
      {title ? <p className="mb-1 font-medium">{title}</p> : null}
      <div className="text-ink-muted">{children}</div>
    </div>
  );
}
