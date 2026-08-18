import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { stubFetch } from '@/test/http';
import { renderWithProviders } from '@/test/render';

import { SyntheticDataBanner } from './SyntheticDataBanner';

/**
 * Data-provenance labelling.
 *
 * The most consequential component in the app: it is what stops a screenshot of
 * generated figures, or a fifteen-minute-old price, from being read as the live
 * market. These tests pin the two claims it must make and the one case where
 * saying nothing is correct.
 */

interface ProviderOverrides {
  is_synthetic?: boolean;
  price_delay_minutes?: number | null;
}

function renderWithProvider(overrides: ProviderOverrides) {
  stubFetch([
    {
      match: '/meta',
      body: {
        provider: {
          name: 'test',
          description: 'Test provider',
          is_synthetic: false,
          price_delay_minutes: null,
          verification_sources: ['PSX filings (PUCARS) - https://dps.psx.com.pk/'],
          ...overrides,
        },
        sectors: [],
        time_horizons: [],
        risk_tolerances: [],
      },
    },
  ]);
  return renderWithProviders(<SyntheticDataBanner />);
}

describe('SyntheticDataBanner', () => {
  it('warns that figures are generated when the provider is synthetic', async () => {
    renderWithProvider({ is_synthetic: true });

    expect(await screen.findByText(/Demonstration data/i)).toBeInTheDocument();
    expect(
      screen.getByText(/every financial figure and price shown here is generated/i),
    ).toBeInTheDocument();
  });

  it('warns about the lag when prices are real but delayed', async () => {
    renderWithProvider({ is_synthetic: false, price_delay_minutes: 15 });

    expect(await screen.findByText(/Delayed prices/i)).toBeInTheDocument();
    expect(screen.getByText(/at least 15 minutes behind the market/i)).toBeInTheDocument();
  });

  it('does not call real data "demonstration data"', async () => {
    const { container } = renderWithProvider({ is_synthetic: false, price_delay_minutes: 15 });

    await screen.findByText(/Delayed prices/i);
    expect(container.textContent).not.toMatch(/generated/i);
    expect(container.textContent).not.toMatch(/Demonstration/i);
  });

  it('says so when the provider cannot state its delay', async () => {
    // `null` is not the same answer as `0`. An unknown lag is worth surfacing,
    // because the alternative is the user assuming the price is current.
    renderWithProvider({ is_synthetic: false, price_delay_minutes: null });

    expect(await screen.findByText(/Delayed prices/i)).toBeInTheDocument();
    expect(screen.getByText(/how far behind they are is not known/i)).toBeInTheDocument();
  });

  it('renders nothing for real, real-time data', async () => {
    const { container } = renderWithProvider({ is_synthetic: false, price_delay_minutes: 0 });

    // Nothing to warn about: the source is still named in the footer.
    await waitFor(() => expect(container).toBeEmptyDOMElement());
  });

  it('renders nothing while metadata is still loading', () => {
    // Flashing a warning that then disappears is worse than waiting a beat - and
    // showing the wrong one would be worse still.
    const { container } = renderWithProvider({ is_synthetic: true });

    expect(container).toBeEmptyDOMElement();
  });

  it('is not dismissible', async () => {
    renderWithProvider({ is_synthetic: true });

    await screen.findByText(/Demonstration data/i);
    // A warning the user can close is a warning that is absent for the rest of
    // the session, so there must be no control that removes it.
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('points the user at a source they can check themselves', async () => {
    renderWithProvider({ is_synthetic: true });

    expect(await screen.findByText(/PSX filings \(PUCARS\)/)).toBeInTheDocument();
  });
});
