import { useMetadata } from '@/features/meta/queries';

/**
 * The synthetic-data warning.
 *
 * This is not decoration. The bundled dataset pairs **real PSX ticker symbols with
 * invented financials**, which is exactly the combination that could be mistaken
 * for real market data in a screenshot. The backend reports
 * `provider.is_synthetic`, and this banner is the frontend's half of honouring it.
 *
 * Deliberately not dismissible, and rendered above the page content rather than as
 * a toast: a warning the user can close is a warning that is absent for the rest of
 * the session.
 *
 * Renders nothing once a provider reports real data - at which point the source is
 * still named in the footer, but there is nothing to warn about.
 */
export function SyntheticDataBanner() {
  const { data, isLoading } = useMetadata();

  // While metadata is loading there is nothing accurate to say, and flashing a
  // warning that then disappears is worse than waiting a beat.
  if (isLoading || !data) return null;
  if (!data.provider.is_synthetic) return null;

  // The sources list has a server-side default, so the schema marks it optional.
  // Only the first is shown; the rest appear on the dashboard.
  const firstSource = (data.provider.verification_sources ?? [])[0]?.split(' - ')[0];

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
