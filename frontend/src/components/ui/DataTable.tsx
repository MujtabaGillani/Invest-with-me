import clsx from 'clsx';
import type { ReactNode } from 'react';

/**
 * A minimal table primitive.
 *
 * Deliberately not a generic data-grid: this application has six tables, all with
 * server-side filtering and no client-side sorting, so a column-definition
 * abstraction would be more code than the tables it replaced. What is centralised
 * is the part worth centralising - alignment and numeric formatting.
 *
 * `numeric` right-aligns and applies tabular figures, which is what makes a column
 * of money readable by comparing digits down the column.
 */

export function Table({
  children,
  className,
}: {
  children: ReactNode;
  className?: string | undefined;
}) {
  return <table className={clsx('w-full border-collapse text-sm', className)}>{children}</table>;
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="bg-surface-sunken border-border border-y">{children}</thead>;
}

export function TBody({ children }: { children: ReactNode }) {
  return <tbody className="divide-border divide-y">{children}</tbody>;
}

export function TR({
  children,
  className,
  onClick,
}: {
  children: ReactNode;
  className?: string | undefined;
  onClick?: (() => void) | undefined;
}) {
  return (
    <tr
      onClick={onClick}
      className={clsx(onClick && 'hover:bg-surface-sunken cursor-pointer', className)}
    >
      {children}
    </tr>
  );
}

interface CellProps {
  children?: ReactNode | undefined;
  /** Right-align and use tabular figures. */
  numeric?: boolean | undefined;
  className?: string | undefined;
  colSpan?: number | undefined;
  /** Tooltip - used for the criteria behind a verdict. */
  title?: string | undefined;
}

export function TH({ children, numeric, className, colSpan }: CellProps) {
  return (
    <th
      scope="col"
      colSpan={colSpan}
      className={clsx(
        'text-ink-muted px-4 py-2.5 text-xs font-medium tracking-wide uppercase',
        numeric ? 'text-right' : 'text-left',
        className,
      )}
    >
      {children}
    </th>
  );
}

export function TD({ children, numeric, className, colSpan, title }: CellProps) {
  return (
    <td
      colSpan={colSpan}
      title={title}
      className={clsx(
        'text-ink px-4 py-3',
        numeric ? 'numeric text-right' : 'text-left',
        className,
      )}
    >
      {children}
    </td>
  );
}

/** A row-header cell, for the first column of a data row. */
export function THRow({ children, className }: CellProps) {
  return (
    <th scope="row" className={clsx('text-ink px-4 py-3 text-left font-medium', className)}>
      {children}
    </th>
  );
}
