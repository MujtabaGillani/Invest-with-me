import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { errorEnvelope, stubFetch } from '@/test/http';
import { renderWithProviders } from '@/test/render';

import { TradeForm } from './TradeForm';

/**
 * Trade entry tests.
 *
 * The two things that matter most here are not layout:
 *
 * 1. **The form must never read as placing an order.** It records something that
 *    already happened at the broker. That ambiguity would be the most dangerous
 *    wording mistake in the whole application.
 * 2. **The submitted payload must be exactly right.** A misplaced fee or a
 *    quantity sent as the wrong field corrupts the cost basis for every future
 *    read, since holdings are replayed from this ledger.
 */

const TRADE_RESPONSE = {
  id: 1,
  symbol: 'LUCK',
  company_name: 'Lucky Cement Limited',
  side: 'buy',
  quantity: '100.0000',
  price: '800.0000',
  fees: '250.0000',
  gross_value: '80000.00',
  net_cash_flow: '-80250.00',
  executed_at: '2025-06-30T00:00:00Z',
  plan_id: null,
  note: null,
};

function fillTrade(user: ReturnType<typeof userEvent.setup>) {
  return async (values: { symbol?: string; shares?: string; price?: string; fees?: string }) => {
    if (values.symbol !== undefined) {
      await user.type(screen.getByLabelText(/^symbol/i), values.symbol);
    }
    if (values.shares !== undefined) {
      await user.type(screen.getByLabelText(/^shares/i), values.shares);
    }
    if (values.price !== undefined) {
      await user.type(screen.getByLabelText(/price per share/i), values.price);
    }
    if (values.fees !== undefined) {
      await user.type(screen.getByLabelText(/^fees/i), values.fees);
    }
  };
}

describe('TradeForm', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it('says plainly that it records a trade rather than placing one', () => {
    stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    expect(screen.getByText(/already gone through at your broker/i)).toBeInTheDocument();
    expect(screen.getByText(/does not place orders/i)).toBeInTheDocument();
  });

  it('keeps submission disabled until symbol, shares and price are all present', async () => {
    const user = userEvent.setup();
    stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);
    const fill = fillTrade(user);

    const submit = screen.getByRole('button', { name: /record purchase/i });
    expect(submit).toBeDisabled();

    await fill({ symbol: 'LUCK' });
    expect(submit).toBeDisabled();

    await fill({ shares: '100' });
    expect(submit).toBeDisabled();

    await fill({ price: '800' });
    expect(submit).toBeEnabled();
  });

  it('shows a running total so a mistyped quantity is caught before submitting', async () => {
    const user = userEvent.setup();
    stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    await fillTrade(user)({ symbol: 'LUCK', shares: '100', price: '800', fees: '250' });

    // A buy costs gross plus fees: 100 x 800 + 250.
    expect(screen.getByText(/total cost/i)).toBeInTheDocument();
    expect(screen.getByText('PKR 80,250.00')).toBeInTheDocument();
  });

  it('nets fees off the proceeds on a sale rather than adding them', async () => {
    const user = userEvent.setup();
    stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    await userEvent.selectOptions(screen.getByLabelText(/^side/i), 'sell');
    await fillTrade(user)({ symbol: 'LUCK', shares: '100', price: '900', fees: '300' });

    // A sale returns gross less fees: 100 x 900 - 300.
    expect(screen.getByText(/net proceeds/i)).toBeInTheDocument();
    expect(screen.getByText('PKR 89,700.00')).toBeInTheDocument();
  });

  it('submits the exact payload the ledger needs', async () => {
    const user = userEvent.setup();
    const http = stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    await fillTrade(user)({ symbol: 'luck', shares: '100', price: '800', fees: '250' });
    await user.click(screen.getByRole('button', { name: /record purchase/i }));

    await waitFor(() => expect(http.callsTo('/portfolio/trades')).toHaveLength(1));
    const call = http.callsTo('/portfolio/trades')[0];

    expect(call?.method).toBe('POST');
    expect(call?.body).toEqual({
      // Upper-cased client-side so the ledger is consistent regardless of typing.
      symbol: 'LUCK',
      side: 'buy',
      // Sent as strings: the backend stores these as Decimal, and a float
      // round-trip would introduce rounding the user never typed.
      quantity: '100',
      price: '800',
      fees: '250',
      executed_at: null,
      note: null,
    });
  });

  it('defaults fees to zero rather than omitting them', async () => {
    const user = userEvent.setup();
    const http = stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    await fillTrade(user)({ symbol: 'LUCK', shares: '10', price: '100' });
    await user.click(screen.getByRole('button', { name: /record purchase/i }));

    await waitFor(() => expect(http.callsTo('/portfolio/trades')).toHaveLength(1));
    expect(http.callsTo('/portfolio/trades')[0]?.body).toMatchObject({ fees: '0' });
  });

  it('presents a business-rule rejection in the server own words', async () => {
    const user = userEvent.setup();
    stubFetch([
      {
        match: '/portfolio/trades',
        status: 422,
        body: errorEnvelope(
          'validation_error',
          'You hold 250 shares of LUCK; the trade sells 400.',
          { symbol: 'LUCK', quantity_held: '250.0000' },
        ),
      },
    ]);
    renderWithProviders(<TradeForm />);

    await userEvent.selectOptions(screen.getByLabelText(/^side/i), 'sell');
    await fillTrade(user)({ symbol: 'LUCK', shares: '400', price: '900' });
    await user.click(screen.getByRole('button', { name: /record sale/i }));

    // Shown as a considered explanation, not a crash - the user needs to correct
    // a figure, not report a bug.
    expect(
      await screen.findByText(/You hold 250 shares of LUCK; the trade sells 400\./),
    ).toBeInTheDocument();
    expect(screen.getByText(/does not fit your ledger/i)).toBeInTheDocument();
  });

  it('clears the amounts after a successful record but keeps the symbol', async () => {
    const user = userEvent.setup();
    stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm />);

    await fillTrade(user)({ symbol: 'LUCK', shares: '100', price: '800' });
    await user.click(screen.getByRole('button', { name: /record purchase/i }));

    expect(await screen.findByText(/^Recorded/)).toBeInTheDocument();
    // Amounts cleared so a second entry cannot accidentally repeat the first,
    // symbol kept because consecutive trades in one company are common.
    expect(screen.getByLabelText(/^shares/i)).toHaveValue('');
    expect(screen.getByLabelText(/price per share/i)).toHaveValue('');
    expect(screen.getByLabelText(/^symbol/i)).toHaveValue('LUCK');
  });

  it('reports when the trade was linked to a plan', async () => {
    const user = userEvent.setup();
    stubFetch([
      {
        match: '/portfolio/trades',
        status: 201,
        body: { ...TRADE_RESPONSE, plan_id: 7 },
      },
    ]);
    renderWithProviders(<TradeForm />);

    await fillTrade(user)({ symbol: 'LUCK', shares: '100', price: '800' });
    await user.click(screen.getByRole('button', { name: /record purchase/i }));

    expect(await screen.findByText(/linked to your plan/i)).toBeInTheDocument();
  });

  it('accepts a back-dated trade', async () => {
    const user = userEvent.setup();
    const http = stubFetch([{ match: '/portfolio/trades', body: TRADE_RESPONSE, status: 201 }]);
    renderWithProviders(<TradeForm defaultSymbol="LUCK" />);

    await fillTrade(user)({ shares: '100', price: '600' });
    await user.type(screen.getByLabelText(/^date/i), '2023-04-11');
    await user.click(screen.getByRole('button', { name: /record purchase/i }));

    await waitFor(() => expect(http.callsTo('/portfolio/trades')).toHaveLength(1));
    const body = http.callsTo('/portfolio/trades')[0]?.body as { executed_at: string };
    expect(body.executed_at).toBe('2023-04-11T00:00:00.000Z');
  });
});
