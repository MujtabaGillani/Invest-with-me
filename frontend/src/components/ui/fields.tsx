import clsx from 'clsx';
import { useId } from 'react';
import type {
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

/**
 * Form controls.
 *
 * Every control here is label-bound via `useId`, so clicking the label focuses the
 * input and a screen reader announces it. This is a form-heavy application - the
 * profile, the checklist, the trade entry - and unlabelled inputs would make it
 * unusable with assistive technology.
 *
 * `hint` is used heavily on purpose: several fields ask the user to commit to a
 * number they may not have thought about before (a stop-loss, a sector cap), and
 * the hint is where the guide's reasoning is repeated at the point of decision.
 */

interface FieldShellProps {
  label: string;
  htmlFor: string;
  hint?: ReactNode | undefined;
  error?: string | undefined;
  required?: boolean | undefined;
  children: ReactNode;
  className?: string | undefined;
}

function FieldShell({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
  className,
}: FieldShellProps) {
  return (
    <div className={clsx('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="text-ink block text-sm font-medium">
        {label}
        {required ? (
          <span className="text-verdict-weak ml-0.5" aria-hidden="true">
            *
          </span>
        ) : null}
      </label>
      {children}
      {error ? (
        <p className="text-verdict-weak text-xs" role="alert">
          {error}
        </p>
      ) : hint ? (
        <p className="text-ink-muted text-xs">{hint}</p>
      ) : null}
    </div>
  );
}

const CONTROL_CLASSES =
  'w-full rounded-md border border-border-strong bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-subtle disabled:bg-surface-sunken disabled:text-ink-subtle';

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'className'> {
  label: string;
  hint?: ReactNode | undefined;
  error?: string | undefined;
}

export function TextField({ label, hint, error, required, ...rest }: TextFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} htmlFor={id} hint={hint} error={error} required={required}>
      <input
        id={id}
        type="text"
        required={required}
        aria-invalid={error ? true : undefined}
        className={clsx(CONTROL_CLASSES, error && 'border-verdict-weak')}
        {...rest}
      />
    </FieldShell>
  );
}

interface NumberFieldProps extends Omit<TextFieldProps, 'type'> {
  /** Rendered inside the control, e.g. `%` or `PKR`. */
  suffix?: string | undefined;
}

/**
 * A numeric input.
 *
 * Uses `inputMode="decimal"` with `type="text"` rather than `type="number"`:
 * number inputs silently discard invalid keystrokes, scroll-wheel over them
 * changes the value, and they reject the trailing decimal point a user types
 * mid-entry. For money, the text input with numeric keyboard hinting is the
 * better trade.
 */
export function NumberField({ label, hint, error, required, suffix, ...rest }: NumberFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} htmlFor={id} hint={hint} error={error} required={required}>
      <div className="relative">
        <input
          id={id}
          type="text"
          inputMode="decimal"
          required={required}
          aria-invalid={error ? true : undefined}
          className={clsx(
            CONTROL_CLASSES,
            'numeric',
            suffix && 'pr-12',
            error && 'border-verdict-weak',
          )}
          {...rest}
        />
        {suffix ? (
          <span className="text-ink-subtle pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm">
            {suffix}
          </span>
        ) : null}
      </div>
    </FieldShell>
  );
}

interface TextAreaFieldProps extends Omit<
  TextareaHTMLAttributes<HTMLTextAreaElement>,
  'id' | 'className'
> {
  label: string;
  hint?: ReactNode | undefined;
  error?: string | undefined;
}

export function TextAreaField({
  label,
  hint,
  error,
  required,
  rows = 4,
  ...rest
}: TextAreaFieldProps) {
  const id = useId();
  return (
    <FieldShell label={label} htmlFor={id} hint={hint} error={error} required={required}>
      <textarea
        id={id}
        rows={rows}
        required={required}
        aria-invalid={error ? true : undefined}
        className={clsx(CONTROL_CLASSES, 'resize-y', error && 'border-verdict-weak')}
        {...rest}
      />
    </FieldShell>
  );
}

export interface SelectOption {
  value: string;
  label: string;
  description?: string | null;
}

interface SelectFieldProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  'id' | 'className' | 'children'
> {
  label: string;
  options: SelectOption[];
  hint?: ReactNode | undefined;
  error?: string | undefined;
  /** Adds a leading blank option, for an optional filter. */
  placeholder?: string | undefined;
}

export function SelectField({
  label,
  options,
  hint,
  error,
  required,
  placeholder,
  value,
  ...rest
}: SelectFieldProps) {
  const id = useId();
  // The selected option's own description, so an enum's meaning is shown at the
  // moment of choosing rather than in a help page.
  const selected = options.find((option) => option.value === value);

  return (
    <FieldShell
      label={label}
      htmlFor={id}
      hint={selected?.description ?? hint}
      error={error}
      required={required}
    >
      <select
        id={id}
        value={value}
        required={required}
        aria-invalid={error ? true : undefined}
        className={clsx(CONTROL_CLASSES, error && 'border-verdict-weak')}
        {...rest}
      >
        {placeholder ? <option value="">{placeholder}</option> : null}
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

interface CheckboxFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'type'> {
  label: ReactNode;
  hint?: ReactNode | undefined;
}

export function CheckboxField({ label, hint, className, ...rest }: CheckboxFieldProps) {
  const id = useId();
  return (
    <div className={clsx('flex gap-2.5', className)}>
      <input
        id={id}
        type="checkbox"
        className="border-border-strong text-accent mt-0.5 size-4 shrink-0 rounded"
        {...rest}
      />
      <div className="min-w-0">
        <label htmlFor={id} className="text-ink block text-sm">
          {label}
        </label>
        {hint ? <p className="text-ink-muted mt-0.5 text-xs">{hint}</p> : null}
      </div>
    </div>
  );
}

/**
 * A three-state answer control for the pre-buy checklist.
 *
 * Three states, not a checkbox, because "not yet answered" and "answered no" are
 * genuinely different and the API distinguishes them. A checkbox would collapse
 * them and make an unfinished checklist look like a failed one.
 */
export function TriStateAnswer({
  question,
  value,
  onChange,
  disabled,
}: {
  question: string;
  value: boolean | null | undefined;
  onChange: (value: boolean) => void;
  disabled?: boolean | undefined;
}) {
  const options: { label: string; answer: boolean }[] = [
    { label: 'Yes', answer: true },
    { label: 'No', answer: false },
  ];

  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <p className="text-ink text-sm">{question}</p>
      <div
        role="group"
        aria-label={question}
        className="border-border-strong flex shrink-0 overflow-hidden rounded-md border"
      >
        {options.map((option) => (
          <button
            key={option.label}
            type="button"
            disabled={disabled}
            aria-pressed={value === option.answer}
            onClick={() => onChange(option.answer)}
            className={clsx(
              'px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed',
              value === option.answer
                ? option.answer
                  ? 'bg-verdict-strong text-white'
                  : 'bg-verdict-weak text-white'
                : 'bg-surface text-ink-muted hover:bg-surface-sunken',
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
