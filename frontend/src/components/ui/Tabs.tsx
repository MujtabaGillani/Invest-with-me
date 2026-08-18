import clsx from 'clsx';
import type { ReactNode } from 'react';

/**
 * A controlled tab strip.
 *
 * Controlled rather than self-managing so the selected tab can live in the URL -
 * a link to a company's technicals should open on that tab. Implements the ARIA
 * tabs pattern, including arrow-key navigation, because this is the main way of
 * moving between the fundamentals and technicals views.
 */

export interface TabDefinition<T extends string> {
  id: T;
  label: string;
  /** Rendered after the label, e.g. an alert count. */
  badge?: ReactNode | undefined;
  /** Disabled tabs explain themselves - "no price history for this company". */
  disabled?: boolean | undefined;
  disabledReason?: string | undefined;
}

interface TabsProps<T extends string> {
  tabs: TabDefinition<T>[];
  active: T;
  onChange: (id: T) => void;
  className?: string | undefined;
}

export function Tabs<T extends string>({ tabs, active, onChange, className }: TabsProps<T>) {
  const enabled = tabs.filter((tab) => !tab.disabled);

  function moveFocus(direction: 1 | -1) {
    const currentIndex = enabled.findIndex((tab) => tab.id === active);
    if (currentIndex === -1) return;
    const nextIndex = (currentIndex + direction + enabled.length) % enabled.length;
    const next = enabled[nextIndex];
    if (next) onChange(next.id);
  }

  return (
    <div
      role="tablist"
      aria-label="View"
      className={clsx('border-border flex gap-1 border-b', className)}
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          moveFocus(1);
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault();
          moveFocus(-1);
        }
      }}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            id={`tab-${tab.id}`}
            aria-selected={isActive}
            aria-controls={`panel-${tab.id}`}
            tabIndex={isActive ? 0 : -1}
            disabled={tab.disabled}
            title={tab.disabled ? tab.disabledReason : undefined}
            onClick={() => onChange(tab.id)}
            className={clsx(
              'flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isActive
                ? 'border-accent text-accent'
                : 'text-ink-muted hover:text-ink border-transparent',
            )}
          >
            {tab.label}
            {tab.badge}
          </button>
        );
      })}
    </div>
  );
}

/** The panel a tab controls. Renders nothing when its tab is not selected. */
export function TabPanel({
  id,
  active,
  children,
}: {
  id: string;
  active: boolean;
  children: ReactNode;
}) {
  if (!active) return null;
  return (
    <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} tabIndex={0}>
      {children}
    </div>
  );
}
