import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { META_RESPONSE, errorEnvelope, stubFetch } from '@/test/http';
import { renderWithProviders } from '@/test/render';
import type { InvestorProfile } from '@/types';

import { ProfileForm } from './ProfileForm';

/**
 * Investor profile form tests.
 *
 * The form deliberately does **not** duplicate the server's validation, so what
 * matters is that it presents the server's rejections usefully: a field error must
 * land on the field it belongs to, and a cross-field error must appear where the
 * user will see it rather than being attached to an arbitrary input.
 */

const SAVED_PROFILE: InvestorProfile = {
  time_horizon: 'long_term',
  risk_tolerance: 'moderate',
  drawdown_tolerance_pct: '30.00',
  investable_capital: '1500000.0000',
  max_position_pct: '15.00',
  max_sector_pct: '35.00',
  emergency_fund_in_place: true,
  investing_borrowed_money: false,
  review_interval_days: 90,
  goals_note: null,
  warnings: [],
};

function stubMetaAnd(profileRoute: Parameters<typeof stubFetch>[0][number]) {
  return stubFetch([{ match: '/meta', body: META_RESPONSE }, profileRoute]);
}

describe('ProfileForm', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('offers the same defaults the server would use when no profile exists', async () => {
    stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={null} />);

    // Shown rather than left blank, so the user can see what would apply if they
    // accept them - an empty form would imply no limits at all.
    expect(await screen.findByLabelText(/largest drop/i)).toHaveValue('30');
    expect(screen.getByLabelText(/most in any one holding/i)).toHaveValue('15');
    expect(screen.getByLabelText(/most in any one sector/i)).toHaveValue('35');
    expect(screen.getByLabelText(/revisit each holding/i)).toHaveValue('90');
    expect(screen.getByRole('button', { name: /save your plan/i })).toBeInTheDocument();
  });

  it('pre-fills from an existing profile and offers to save changes', async () => {
    stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={SAVED_PROFILE} />);

    expect(await screen.findByLabelText(/investable capital/i)).toHaveValue('1500000.0000');
    expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument();
  });

  it('sends decimals as strings so nothing is lost to float rounding', async () => {
    const user = userEvent.setup();
    const http = stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.clear(await screen.findByLabelText(/investable capital/i));
    await user.type(screen.getByLabelText(/investable capital/i), '1250000.50');
    await user.click(screen.getByRole('button', { name: /save your plan/i }));

    await waitFor(() => expect(http.callsTo('/profile')).toHaveLength(1));
    const call = http.callsTo('/profile')[0];

    expect(call?.method).toBe('PUT');
    expect(call?.body).toMatchObject({
      time_horizon: 'long_term',
      risk_tolerance: 'moderate',
      investable_capital: '1250000.50',
      max_position_pct: '15',
      max_sector_pct: '35',
      // An integer field, sent as a number.
      review_interval_days: 90,
      goals_note: null,
    });
  });

  it('puts a field error on the field it belongs to', async () => {
    const user = userEvent.setup();
    stubMetaAnd({
      match: '/profile',
      status: 422,
      body: errorEnvelope('request_validation_error', 'The request could not be processed.', {
        errors: [
          {
            location: ['body', 'max_position_pct'],
            message: 'Input should be less than or equal to 100',
            type: 'less_than_equal',
          },
        ],
      }),
    });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.click(await screen.findByRole('button', { name: /save your plan/i }));

    const error = await screen.findByText(/less than or equal to 100/i);
    expect(error).toBeInTheDocument();
    expect(error).toHaveAttribute('role', 'alert');
    // Marked invalid so assistive technology announces it, not just coloured.
    expect(screen.getByLabelText(/most in any one holding/i)).toHaveAttribute(
      'aria-invalid',
      'true',
    );
  });

  it('shows a cross-field rejection above the form, not against one input', async () => {
    const user = userEvent.setup();
    stubMetaAnd({
      match: '/profile',
      status: 422,
      body: errorEnvelope('request_validation_error', 'The request could not be processed.', {
        errors: [
          {
            // A whole-body error: it belongs to no single field.
            location: ['body'],
            message:
              'Value error, max_position_pct cannot exceed max_sector_pct - a single holding cannot be allowed a larger share of the portfolio than the whole sector it belongs to.',
            type: 'value_error',
          },
        ],
      }),
    });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.click(await screen.findByRole('button', { name: /save your plan/i }));

    expect(await screen.findByText(/cannot exceed max_sector_pct/i)).toBeInTheDocument();
  });

  it('falls back to a general error when the failure is not a validation one', async () => {
    const user = userEvent.setup();
    stubMetaAnd({
      match: '/profile',
      status: 500,
      body: errorEnvelope('internal_error', 'Something went wrong handling this request.'),
    });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.click(await screen.findByRole('button', { name: /save your plan/i }));

    expect(await screen.findByText(/could not save your plan/i)).toBeInTheDocument();
    // The request id is surfaced so a report can quote something traceable.
    expect(screen.getByText(/test-request-id/)).toBeInTheDocument();
  });

  it('confirms a successful save', async () => {
    const user = userEvent.setup();
    stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.click(await screen.findByRole('button', { name: /save your plan/i }));

    expect(await screen.findByText('Saved.')).toBeInTheDocument();
  });

  it('explains the money-hygiene questions rather than just asking them', async () => {
    stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={null} />);

    // The guide's reasoning is repeated at the point of decision, which is the only
    // place it can actually change an answer.
    expect(await screen.findByText(/withdrawn at the worst possible moment/i)).toBeInTheDocument();
    expect(screen.getByText(/repayment schedule decides when you sell/i)).toBeInTheDocument();
    expect(screen.getByText(/Not rent, not an emergency fund/i)).toBeInTheDocument();
  });

  it('sends the borrowed-money declaration when ticked', async () => {
    const user = userEvent.setup();
    const http = stubMetaAnd({ match: '/profile', body: SAVED_PROFILE });
    renderWithProviders(<ProfileForm profile={null} />);

    await user.click(await screen.findByLabelText(/some of this money is borrowed/i));
    await user.click(screen.getByRole('button', { name: /save your plan/i }));

    await waitFor(() => expect(http.callsTo('/profile')).toHaveLength(1));
    expect(http.callsTo('/profile')[0]?.body).toMatchObject({ investing_borrowed_money: true });
  });
});
