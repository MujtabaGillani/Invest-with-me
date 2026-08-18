import { useMetadata } from '@/features/meta/queries';

/**
 * The data-provenance banner.
 *
 * This is not decoration. It states, permanently and undismissibly, what the
 * numbers on screen actually are. There are two things worth saying, and which
 * one applies depends on the active provider:
 *
 * 1. **The figures are invented.** The bundled dataset pairs **real PSX ticker
 *    symbols with generated financials**, which is exactly the combination that
 *    could be mistaken for real market data in a screenshot.
 * 2. **The prices are real but delayed.** Unlicensed public PSX sources are
 *    always behind the market. Someone deciding when to buy or sell is entitled
 *    to know they are looking at a photograph rather than the market, so a
 *    non-zero `provider.price_delay_minutes` is called out just as prominently.
 *
 * Deliberately not dismissible, and rendered above the page content rather than
 * as a toast: a warning the user can close is a warning that is absent for the
 * rest of the session.
 *
 * Renders nothing only when the data is real *and* the provider reports real-time
 * prices, which today means a licensed feed.
 */
export function SyntheticDataBanner() {
  const { data, isLoading } = useMetadata();

  // While metadata is loading there is nothing accurate to say, and flashing a
  // warning that then disappears is worse than waiting a beat.
  if (isLoading || !data) return null;

  const { is_synthetic: isSynthetic, price_delay_minutes: delayMinutes } = data.provider;

  // The sources list has a server-side default, so the schema marks it optional.
  // Only the first is shown; the rest appear on the dashboard.
  const firstSource = (data.provider.verification_sources ?? [])[0]?.split(' - ')[0];

  if (isSynthetic) {
    return (
      <div
        role="note"
        className="border-synthetic/30 bg-synthetic-bg text-ink border-b px-4 py-2.5 text-sm sm:px-6"
      >
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-synthetic font-semibold">Demonstration data.</span>
          <span className="text-ink-muted">
            Ticker symbols and sectors are real PSX listings, but every financial figure and price
            shown here is generated. Do not use any of it for a real decision.
          </span>
          {firstSource ? (
            <span className="text-ink-subtle">Check real figures at {firstSource}.</span>
          ) : null}
        </div>
      </div>
    );
  }

  // Real data, real time: nothing to warn about. The source is still named in
  // the footer. `null` and `0` are different answers here - null means the
  // provider cannot say how stale its prices are, which is itself worth saying.
  if (delayMinutes === 0) return null;

  const delayText =
    delayMinutes == null
      ? 'These prices may not be current, and how far behind they are is not known.'
      : `These prices are at least ${delayMinutes} minutes behind the market.`;

  return (
    <div
      role="note"
      className="border-synthetic/30 bg-synthetic-bg text-ink border-b px-4 py-2.5 text-sm sm:px-6"
    >
      <div className="mx-auto flex max-w-[1400px] flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-synthetic font-semibold">Delayed prices.</span>
        <span className="text-ink-muted">
          {delayText} Treat them as a recent reading, not the current market price, and confirm on
          your broker's screen before acting.
        </span>
        {firstSource ? (
          <span className="text-ink-subtle">Check figures at {firstSource}.</span>
        ) : null}
      </div>
    </div>
  );
}
