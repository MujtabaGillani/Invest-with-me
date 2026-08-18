import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  LoadingState,
  Notice,
  SeverityBadge,
  StatRow,
  StatTile,
} from '@/components/ui';
import { useAlerts, useEvaluateAlerts } from '@/features/alerts/queries';
import { useMetadata } from '@/features/meta/queries';
import { usePlans } from '@/features/plans/queries';
import { usePortfolio } from '@/features/portfolio/queries';
import { useProfile } from '@/features/profile/queries';
import { useWatchlist } from '@/features/watchlist/queries';
import { formatMoney, formatPercent } from '@/lib/format';

/**
 * The dashboard.
 *
 * Ordered by what needs the user's attention rather than by what is most impressive
 * to look at: an unwritten profile first, then alerts, then drafts left unfinished,
 * then the portfolio. A dashboard that leads with a big portfolio number trains the
 * user to check their balance, which is the opposite of the habit this tool exists to
 * support.
 */
export function DashboardPage() {
  const { data: profile, isPending: profilePending } = useProfile();
  const { data: portfolio } = usePortfolio();
  const { data: alerts } = useAlerts(false);
  const { data: plans } = usePlans({ status: 'draft' });
  const { data: watchlist } = useWatchlist();
  const { data: metadata } = useMetadata();
  const evaluate = useEvaluateAlerts();

  if (profilePending) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }

  const openAlerts = alerts ?? [];
  const drafts = plans?.items ?? [];
  const summary = portfolio?.summary;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Where things stand against the rules you have set for yourself."
      />

      <div className="space-y-5">
        {/* The guide's first step. Shown until it is done, because everything else
            is measured against it. */}
        {profile === null ? (
          <Card>
            <CardHeader
              title="Start by writing down your own goals"
              description="Before looking at any company."
            />
            <CardBody>
              <p className="text-ink-muted text-sm">
                How long you can leave the money alone, how large a fall you could hold through, and
                how much of your portfolio any single holding may take. Those answers drive the
                position-size check on every plan and the concentration warnings on your portfolio -
                without them, this tool falls back to conservative defaults you did not choose.
              </p>
              <div className="mt-4">
                <Link to="/profile">
                  <Button variant="primary">Write your plan</Button>
                </Link>
              </div>
            </CardBody>
          </Card>
        ) : null}

        {summary && summary.holdings_count > 0 ? (
          <StatRow>
            <StatTile
              label="Portfolio value"
              value={formatMoney(summary.total_market_value, { abbreviate: true })}
              detail={`${summary.holdings_count} holdings, ${summary.sectors_held} sectors`}
            />
            <StatTile
              label="Unrealised"
              value={formatPercent(summary.total_unrealised_pl_pct, { signed: true })}
              detail={formatMoney(summary.total_unrealised_pl, { abbreviate: true })}
              tone="signed"
              signedFrom={summary.total_unrealised_pl}
            />
            <StatTile
              label="Without exit rules"
              value={summary.holdings_without_exit_rules ?? 0}
              detail={
                (summary.holdings_without_exit_rules ?? 0) > 0
                  ? 'Decide these before you need them'
                  : 'Every holding has a plan'
              }
              tone={(summary.holdings_without_exit_rules ?? 0) > 0 ? 'default' : 'muted'}
            />
            <StatTile
              label="Open alerts"
              value={openAlerts.length}
              detail={openAlerts.length === 0 ? 'Nothing outstanding' : 'Your own rules'}
              tone={openAlerts.length > 0 ? 'default' : 'muted'}
            />
          </StatRow>
        ) : null}

        <Card>
          <CardHeader
            title="Needs your attention"
            description="Rules you set for yourself that have been crossed."
            actions={
              <Button
                size="sm"
                pending={evaluate.isPending}
                pendingLabel="Checking…"
                onClick={() => evaluate.mutate()}
              >
                Re-check
              </Button>
            }
          />
          {openAlerts.length === 0 ? (
            <EmptyState
              title="Nothing outstanding"
              description="No profit target, stop-loss, concentration limit or review interval has been crossed."
            />
          ) : (
            <CardBody className="divide-border divide-y">
              {openAlerts.slice(0, 5).map((alert) => (
                <div key={alert.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                  <SeverityBadge severity={alert.severity} />
                  <p className="text-ink min-w-0 flex-1 text-sm">{alert.message}</p>
                </div>
              ))}
              {openAlerts.length > 5 ? (
                <div className="pt-3">
                  <Link to="/alerts" className="text-accent text-sm hover:underline">
                    See all {openAlerts.length} alerts
                  </Link>
                </div>
              ) : null}
            </CardBody>
          )}
        </Card>

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader
              title="Unfinished plans"
              description="Drafts you have not committed to yet."
            />
            {drafts.length === 0 ? (
              <EmptyState
                title="No drafts open"
                description="Start a plan from any company page to work through the pre-buy checklist."
              />
            ) : (
              <CardBody className="divide-border divide-y">
                {drafts.slice(0, 5).map((plan) => (
                  <div
                    key={plan.id}
                    className="flex items-baseline justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                  >
                    <Link
                      to={`/plans/${plan.id}`}
                      className="text-accent text-sm font-medium hover:underline"
                    >
                      {plan.symbol}
                    </Link>
                    <span className="text-ink-muted text-xs">
                      {(plan.readiness.blocking_reasons ?? []).length} still to settle
                    </span>
                  </div>
                ))}
              </CardBody>
            )}
          </Card>

          <Card>
            <CardHeader title="Watchlist" description="Researching, not yet owned." />
            {(watchlist ?? []).length === 0 ? (
              <EmptyState
                title="Nothing watched"
                description="Add a company along with the reason you are interested."
              />
            ) : (
              <CardBody className="divide-border divide-y">
                {(watchlist ?? []).slice(0, 5).map((item) => (
                  <div
                    key={item.id}
                    className="flex items-baseline justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                  >
                    <Link
                      to={`/companies/${item.symbol}`}
                      className="text-accent text-sm font-medium hover:underline"
                    >
                      {item.symbol}
                    </Link>
                    <span
                      className={
                        item.entry_price_reached
                          ? 'text-verdict-strong text-xs'
                          : 'text-ink-muted text-xs'
                      }
                    >
                      {item.target_entry_price
                        ? item.entry_price_reached
                          ? 'At your entry price'
                          : `${formatPercent(item.distance_to_target_pct)} to your entry price`
                        : 'No entry price set'}
                    </span>
                  </div>
                ))}
              </CardBody>
            )}
          </Card>
        </div>

        {/* Guide section 8, made actionable: where to check the real numbers. */}
        {metadata && (metadata.provider.verification_sources ?? []).length > 0 ? (
          <Notice title="Check the figures yourself">
            <ul className="mt-1 space-y-0.5">
              {(metadata.provider.verification_sources ?? []).map((source) => (
                <li key={source}>{source}</li>
              ))}
            </ul>
          </Notice>
        ) : null}
      </div>
    </>
  );
}
