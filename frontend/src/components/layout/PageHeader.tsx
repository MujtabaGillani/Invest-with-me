import type { ReactNode } from 'react';

/**
 * The heading block at the top of every page.
 *
 * `description` is used on every screen rather than being optional-in-practice: a
 * user arriving at "Trade plans" needs one sentence explaining what a plan is for
 * before the table means anything.
 */
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode | undefined;
  actions?: ReactNode | undefined;
}) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-ink text-xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="text-ink-muted mt-1 max-w-2xl text-sm">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}
