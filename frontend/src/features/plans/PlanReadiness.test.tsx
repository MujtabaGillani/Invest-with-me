import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test/render';
import type { TradePlanDetail } from '@/types';

import { PlanReadiness } from './PlanReadiness';

/**
 * The readiness panel is the user-facing half of the product's one hard rule, so
 * these tests check the things that would quietly defeat it:
 *
 * * the commit button must be disabled while anything is outstanding
 * * every blocking reason must be *shown*, not summarised as a count
 * * advisory notes must not disable anything - they inform, and the user decides
 */

function plan(overrides: Partial<TradePlanDetail> = {}): TradePlanDetail {
  return {
    id: 1,
    company_id: 1,
    symbol: 'LUCK',
    company_name: 'Lucky Cement Limited',
    status: 'draft',
    checklist: [],
    thesis: null,
    invalidation_note: null,
    intended_amount: null,
    profit_target_pct: null,
    stop_loss_pct: null,
    committed_at: null,
    last_reviewed_at: null,
    created_at: '2025-06-01T10:00:00Z',
    updated_at: '2025-06-01T10:00:00Z',
    reviews: [],
    readiness: {
      can_commit: false,
      checklist_complete: false,
      has_exit_rules: false,
      unanswered_items: [],
      failed_items: [],
      blocking_reasons: [],
      advisory_notes: [],
    },
    ...overrides,
  };
}

function commitButton() {
  return screen.getByRole('button', { name: /commit to this plan/i });
}

describe('PlanReadiness', () => {
  it('lists every blocking reason rather than a count', () => {
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          readiness: {
            can_commit: false,
            checklist_complete: false,
            has_exit_rules: false,
            unanswered_items: ['position_size_appropriate'],
            failed_items: [],
            blocking_reasons: [
              'Not yet answered: Is this purchase small enough?',
              'No stop-loss set. Decide before buying how large a loss you are willing to accept.',
            ],
            advisory_notes: [],
          },
        })}
      />,
    );

    expect(
      screen.getByText(/Not yet answered: Is this purchase small enough\?/),
    ).toBeInTheDocument();
    expect(screen.getByText(/No stop-loss set/)).toBeInTheDocument();
    expect(screen.getByText(/2 things still to settle/)).toBeInTheDocument();
  });

  it('disables the commit button while anything is outstanding', () => {
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          readiness: {
            can_commit: false,
            checklist_complete: false,
            has_exit_rules: false,
            unanswered_items: [],
            failed_items: [],
            blocking_reasons: ['No profit target set.'],
            advisory_notes: [],
          },
        })}
      />,
    );

    expect(commitButton()).toBeDisabled();
  });

  it('enables the commit button once nothing is outstanding', () => {
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          readiness: {
            can_commit: true,
            checklist_complete: true,
            has_exit_rules: true,
            unanswered_items: [],
            failed_items: [],
            blocking_reasons: [],
            advisory_notes: [],
          },
        })}
      />,
    );

    expect(commitButton()).toBeEnabled();
    expect(screen.getByText(/Nothing outstanding/)).toBeInTheDocument();
  });

  it('does not let an advisory note block committing', () => {
    // A thin thesis or an unusual target can both be deliberate; the app points
    // them out and then gets out of the way.
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          readiness: {
            can_commit: true,
            checklist_complete: true,
            has_exit_rules: true,
            unanswered_items: [],
            failed_items: [],
            blocking_reasons: [],
            advisory_notes: ['The thesis is empty or very short.'],
          },
        })}
      />,
    );

    expect(commitButton()).toBeEnabled();
    expect(screen.getByText(/The thesis is empty or very short/)).toBeInTheDocument();
    expect(screen.getByText(/do not block anything/i)).toBeInTheDocument();
  });

  it('states that committing does not buy anything', () => {
    // The most dangerous possible ambiguity in this application.
    renderWithProviders(<PlanReadiness plan={plan()} />);
    expect(screen.getByText(/does not buy\s+anything/)).toBeInTheDocument();
  });

  it('offers no commit button once the plan is no longer a draft', () => {
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          status: 'executed',
          readiness: {
            can_commit: true,
            checklist_complete: true,
            has_exit_rules: true,
            unanswered_items: [],
            failed_items: [],
            blocking_reasons: [],
            advisory_notes: [],
          },
        })}
      />,
    );

    expect(screen.queryByRole('button', { name: /commit to this plan/i })).not.toBeInTheDocument();
  });

  it('reports the position size against the users own limit', () => {
    renderWithProviders(
      <PlanReadiness
        plan={plan({
          position_sizing: {
            intended_amount: '400000.00',
            portfolio_value: '0.00',
            sizing_base: '1000000.00',
            max_position_pct: '10.00',
            suggested_max_amount: '100000.00',
            exceeds_limit: true,
            resulting_weight_pct: '28.57',
            commentary: 'At PKR 400,000.00 this position would be 28.57% of your portfolio.',
          },
        })}
      />,
    );

    expect(screen.getByText(/Your limit allows/)).toBeInTheDocument();
    // Thousands abbreviate to one decimal place; see formatMoney.
    expect(screen.getByText('PKR 100.0k')).toBeInTheDocument();
    expect(screen.getByText('28.57%')).toBeInTheDocument();
    expect(screen.getByText(/would be 28\.57% of your portfolio/)).toBeInTheDocument();
  });
});
