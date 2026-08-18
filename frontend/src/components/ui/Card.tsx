import clsx from 'clsx';
import type { ReactNode } from 'react';

/**
 * The standard content container.
 *
 * Composed of separate header and body parts rather than taking a `title` prop,
 * so a header can hold a filter control or a badge without the Card growing a new
 * prop for every case.
 */

interface CardProps {
  children: ReactNode;
  className?: string | undefined;
}

export function Card({ children, className }: CardProps) {
  return (
    <section
      className={clsx(
        'bg-surface-raised border-border rounded-lg border shadow-[0_1px_2px_rgba(16,24,40,0.04)]',
        className,
      )}
    >
      {children}
    </section>
  );
}

interface CardHeaderProps {
  title: ReactNode;
  /** One line under the title. Use it for context, not for instructions. */
  description?: ReactNode | undefined;
  /** Rendered right-aligned: a filter, a badge, an action. */
  actions?: ReactNode | undefined;
  className?: string | undefined;
}

export function CardHeader({ title, description, actions, className }: CardHeaderProps) {
  return (
    <header
      className={clsx(
        'border-border flex items-start justify-between gap-4 border-b px-5 py-4',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-ink text-base font-semibold">{title}</h2>
        {description ? <p className="text-ink-muted mt-1 text-sm">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function CardBody({ children, className }: CardProps) {
  return <div className={clsx('px-5 py-4', className)}>{children}</div>;
}

/** For a body that holds a full-bleed table, where padding would misalign it. */
export function CardBodyFlush({ children, className }: CardProps) {
  return <div className={clsx('overflow-x-auto', className)}>{children}</div>;
}

export function CardFooter({ children, className }: CardProps) {
  return (
    <footer className={clsx('border-border bg-surface-sunken border-t px-5 py-3', className)}>
      {children}
    </footer>
  );
}
