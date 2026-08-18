import clsx from 'clsx';
import type { ButtonHTMLAttributes, ReactNode } from 'react';

/**
 * Buttons.
 *
 * `pending` is a first-class prop rather than something each caller wires up: the
 * mutations behind these buttons record trades and commitments, and a
 * double-submitted buy is a real financial consequence. Setting `pending` disables
 * the button and says what is happening.
 */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md';

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-accent text-white hover:bg-accent-hover disabled:bg-ink-subtle',
  secondary:
    'bg-surface border border-border-strong text-ink hover:bg-surface-sunken disabled:text-ink-subtle',
  ghost: 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
  // Used for irreversible-feeling actions such as abandoning a plan. Not for
  // "sell" - the app never presents selling as a destructive action to avoid.
  danger: 'bg-surface border border-verdict-weak/40 text-verdict-weak hover:bg-verdict-weak-bg',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'px-2.5 py-1.5 text-xs',
  md: 'px-3.5 py-2 text-sm',
};

interface ButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  /** Shows a spinner and disables the button. */
  pending?: boolean;
  /** Replaces the label while pending, e.g. "Recording…". */
  pendingLabel?: string | undefined;
  className?: string | undefined;
}

export function Button({
  children,
  variant = 'secondary',
  size = 'md',
  pending = false,
  pendingLabel,
  disabled,
  type = 'button',
  className,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled === true || pending}
      aria-busy={pending}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-70',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        className,
      )}
      {...rest}
    >
      {pending ? (
        <>
          <span
            aria-hidden="true"
            className="size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"
          />
          {pendingLabel ?? children}
        </>
      ) : (
        children
      )}
    </button>
  );
}
