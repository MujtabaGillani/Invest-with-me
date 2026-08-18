import { useState } from 'react';

import {
  Button,
  CheckboxField,
  ErrorState,
  Notice,
  NumberField,
  SelectField,
  TextAreaField,
} from '@/components/ui';
import { toSelectOptions, useMetadata } from '@/features/meta/queries';
import { isApiError } from '@/lib/apiClient';
import type { InvestorProfile, InvestorProfileInput } from '@/types';

import { useSaveProfile } from './queries';

/**
 * The investor profile form - guide section 1, "start with your own goals".
 *
 * Field values are held as **strings**, not numbers. A number-typed state cannot
 * represent "the user has cleared the box and is about to type", and coercing on
 * every keystroke fights the user mid-entry. The API accepts numeric strings for
 * its `Decimal` fields, so the strings go straight through.
 *
 * Validation is deliberately left to the server. The one cross-field rule
 * (`max_position_pct <= max_sector_pct`) is enforced in the API schema, and
 * duplicating it here would create two places for it to be wrong. What this form
 * does instead is surface the server's field errors against the right inputs.
 */

interface ProfileFormProps {
  /** The existing profile, or null when none has been written yet. */
  profile: InvestorProfile | null;
  onSaved?: () => void;
}

interface FormState {
  time_horizon: string;
  risk_tolerance: string;
  drawdown_tolerance_pct: string;
  investable_capital: string;
  max_position_pct: string;
  max_sector_pct: string;
  review_interval_days: string;
  emergency_fund_in_place: boolean;
  investing_borrowed_money: boolean;
  goals_note: string;
}

/** Defaults match the server's, so an unwritten profile shows what it would use. */
function initialState(profile: InvestorProfile | null): FormState {
  return {
    time_horizon: profile?.time_horizon ?? 'long_term',
    risk_tolerance: profile?.risk_tolerance ?? 'moderate',
    drawdown_tolerance_pct: profile?.drawdown_tolerance_pct ?? '30',
    investable_capital: profile?.investable_capital ?? '',
    max_position_pct: profile?.max_position_pct ?? '15',
    max_sector_pct: profile?.max_sector_pct ?? '35',
    review_interval_days: String(profile?.review_interval_days ?? 90),
    emergency_fund_in_place: profile?.emergency_fund_in_place ?? false,
    investing_borrowed_money: profile?.investing_borrowed_money ?? false,
    goals_note: profile?.goals_note ?? '',
  };
}

export function ProfileForm({ profile, onSaved }: ProfileFormProps) {
  const [form, setForm] = useState<FormState>(() => initialState(profile));
  const { data: metadata } = useMetadata();
  const save = useSaveProfile();

  /** Server-side field errors, keyed by field name. */
  const fieldErrors = new Map<string, string>();
  if (isApiError(save.error)) {
    for (const error of save.error.fieldErrors) {
      // Location is ["body", "field_name"]; the last element is the field.
      const field = error.location[error.location.length - 1];
      if (typeof field === 'string') fieldErrors.set(field, error.message);
    }
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();

    const payload: InvestorProfileInput = {
      time_horizon: form.time_horizon as InvestorProfileInput['time_horizon'],
      risk_tolerance: form.risk_tolerance as InvestorProfileInput['risk_tolerance'],
      drawdown_tolerance_pct: form.drawdown_tolerance_pct || '0',
      investable_capital: form.investable_capital || '0',
      max_position_pct: form.max_position_pct || '15',
      max_sector_pct: form.max_sector_pct || '35',
      review_interval_days: Number(form.review_interval_days) || 90,
      emergency_fund_in_place: form.emergency_fund_in_place,
      investing_borrowed_money: form.investing_borrowed_money,
      goals_note: form.goals_note.trim() === '' ? null : form.goals_note.trim(),
    };

    save.mutate(payload, { onSuccess: () => onSaved?.() });
  }

  // A cross-field problem is reported by the server against the whole body rather
  // than one field, so it is shown above the form.
  const formLevelError =
    isApiError(save.error) && save.error.fieldErrors.some((error) => error.location.length <= 1)
      ? save.error.fieldErrors.find((error) => error.location.length <= 1)?.message
      : undefined;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {formLevelError ? <Notice tone="caution">{formLevelError}</Notice> : null}

      <fieldset className="space-y-4">
        <legend className="text-ink text-sm font-semibold">Time horizon and risk</legend>

        <SelectField
          label="How long can you leave this money alone?"
          options={toSelectOptions(metadata?.time_horizons)}
          value={form.time_horizon}
          onChange={(event) => update('time_horizon', event.target.value)}
          error={fieldErrors.get('time_horizon')}
          required
        />

        <SelectField
          label="How would you describe your risk tolerance?"
          options={toSelectOptions(metadata?.risk_tolerances)}
          value={form.risk_tolerance}
          onChange={(event) => update('risk_tolerance', event.target.value)}
          error={fieldErrors.get('risk_tolerance')}
          required
        />

        <NumberField
          label="Largest drop you could hold through without selling"
          suffix="%"
          value={form.drawdown_tolerance_pct}
          onChange={(event) => update('drawdown_tolerance_pct', event.target.value)}
          error={fieldErrors.get('drawdown_tolerance_pct')}
          hint="Individual PSX stocks routinely move 30% or more. Answer honestly rather than aspirationally - this figure is compared against your plans later."
        />
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-ink text-sm font-semibold">How much, and how concentrated</legend>

        <NumberField
          label="Investable capital"
          suffix="PKR"
          value={form.investable_capital}
          onChange={(event) => update('investable_capital', event.target.value)}
          error={fieldErrors.get('investable_capital')}
          hint="Money you can afford to have tied up, or to lose. Not rent, not an emergency fund, not a debt repayment."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            label="Most in any one holding"
            suffix="%"
            value={form.max_position_pct}
            onChange={(event) => update('max_position_pct', event.target.value)}
            error={fieldErrors.get('max_position_pct')}
            hint="Checked against every plan you write and every position you hold."
          />
          <NumberField
            label="Most in any one sector"
            suffix="%"
            value={form.max_sector_pct}
            onChange={(event) => update('max_sector_pct', event.target.value)}
            error={fieldErrors.get('max_sector_pct')}
            hint="Companies in one sector tend to fall together. Cannot be lower than your single-holding limit."
          />
        </div>

        <NumberField
          label="Revisit each holding every"
          suffix="days"
          value={form.review_interval_days}
          onChange={(event) => update('review_interval_days', event.target.value)}
          error={fieldErrors.get('review_interval_days')}
          hint="How often you will re-check that the reason you bought something still holds. Between 7 and 730 days."
        />
      </fieldset>

      <fieldset className="space-y-3">
        <legend className="text-ink text-sm font-semibold">Where the money comes from</legend>

        <CheckboxField
          label="I have an emergency fund I am not investing"
          hint="Money you might need at short notice tends to get withdrawn at the worst possible moment."
          checked={form.emergency_fund_in_place}
          onChange={(event) => update('emergency_fund_in_place', event.target.checked)}
        />

        <CheckboxField
          label="Some of this money is borrowed"
          hint="If this is true, a market fall costs you the loss and the interest, and the repayment schedule decides when you sell rather than your own plan."
          checked={form.investing_borrowed_money}
          onChange={(event) => update('investing_borrowed_money', event.target.checked)}
        />
      </fieldset>

      <TextAreaField
        label="What are you trying to achieve?"
        value={form.goals_note}
        onChange={(event) => update('goals_note', event.target.value)}
        error={fieldErrors.get('goals_note')}
        hint="Optional, but the guide's advice is to write this down before looking at any company - it will matter more than any single stock pick."
        placeholder="For example: long-term holdings funded from savings I will not need for at least five years."
      />

      {save.isError && fieldErrors.size === 0 && !formLevelError ? (
        <ErrorState error={save.error} title="Could not save your plan" />
      ) : null}

      <div className="flex items-center gap-3">
        <Button type="submit" variant="primary" pending={save.isPending} pendingLabel="Saving…">
          {profile ? 'Save changes' : 'Save your plan'}
        </Button>
        {save.isSuccess && !save.isPending ? (
          <span className="text-verdict-strong text-sm">Saved.</span>
        ) : null}
      </div>
    </form>
  );
}
