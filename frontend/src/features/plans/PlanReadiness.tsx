import { Button, Card, CardBody, CardHeader, Notice, StatTile } from '@/components/ui';
import { isApiError } from '@/lib/apiClient';
import { formatMoney, formatPercent } from '@/lib/format';
import type { PositionSizingCheck, TradePlanDetail } from '@/types';

import { useCommitPlan } from './queries';

/**
 * Whether a plan can be committed to, and why not.
 *
 * The server returns explicit `blocking_reasons` rather than a single boolean, so
 * this panel lists exactly what is missing instead of greying out a button and
 * leaving the user to guess. That distinction is the difference between a rule that
 * teaches and one that just obstructs.
 *
 * Blocking reasons and advisory notes are visually separate. Blocking reasons are
 * the invariant; advisory notes are the app pointing something out and then getting
 * out of the way - a thin thesis or a target smaller than the stop can both be
 * deliberate, and the user's judgement wins.
 */
export function PlanReadiness({ plan }: { plan: TradePlanDetail }) {
  const commit = useCommitPlan();
  const { readiness } = plan;
  const isDraft = plan.status === 'draft';

  // Both lists have server-side defaults, so the schema marks them optional.
  // Absent means "none", which is exactly what an empty array renders as.
  const blocking = readiness.blocking_reasons ?? [];
  const advisory = readiness.advisory_notes ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={isDraft ? 'Ready to commit?' : 'Commitment'}
          description={
            isDraft
              ? 'All five answers yes, plus a profit target and a stop-loss.'
              : 'What you committed to before buying.'
          }
        />
        <CardBody className="space-y-4">
          {blocking.length > 0 ? (
            <div>
              <p className="text-ink mb-2 text-sm font-medium">
                {blocking.length} thing
                {blocking.length === 1 ? '' : 's'} still to settle
              </p>
              <ul className="space-y-1.5">
                {blocking.map((reason) => (
                  <li
                    key={reason}
                    className="text-ink-muted border-verdict-weak/50 border-l-2 pl-3 text-sm"
                  >
                    {reason}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Notice tone="positive" title="Nothing outstanding">
              The checklist is complete and both exit rules are set.
            </Notice>
          )}

          {advisory.length > 0 ? (
            <div>
              <p className="text-ink-muted mb-2 text-xs font-medium tracking-wide uppercase">
                Worth considering — these do not block anything
              </p>
              <ul className="space-y-1.5">
                {advisory.map((note) => (
                  <li key={note} className="text-ink-muted border-border border-l-2 pl-3 text-sm">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {isDraft ? (
            <div>
              <Button
                variant="primary"
                disabled={!readiness.can_commit}
                pending={commit.isPending}
                pendingLabel="Committing…"
                onClick={() => commit.mutate(plan.id)}
              >
                Commit to this plan
              </Button>
              <p className="text-ink-subtle mt-2 text-xs">
                Committing records the decision and its exit rules. It does not buy anything —
                record the trade separately once you have actually bought.
              </p>
              {commit.isError ? (
                <div className="mt-3">
                  <p className="text-verdict-weak text-sm">
                    {isApiError(commit.error) ? commit.error.message : 'Could not commit.'}
                  </p>
                  {isApiError(commit.error) && commit.error.blockingReasons.length > 0 ? (
                    <ul className="text-ink-muted mt-1 list-inside list-disc text-xs">
                      {commit.error.blockingReasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </CardBody>
      </Card>

      {plan.position_sizing ? <PositionSizing sizing={plan.position_sizing} /> : null}
    </div>
  );
}

/**
 * The answer to pre-buy question five, computed rather than asserted.
 *
 * The weight shown is the share of the portfolio the position would be *after* it
 * settles, which is the figure the user will actually be carrying.
 */
function PositionSizing({ sizing }: { sizing: PositionSizingCheck }) {
  return (
    <Card>
      <CardHeader
        title="Position size"
        description="Measured against the single-holding limit in your own profile."
      />
      <CardBody className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <StatTile
            label="Your limit allows"
            value={formatMoney(sizing.suggested_max_amount, { abbreviate: true })}
            detail={`${formatPercent(sizing.max_position_pct, { decimals: 0 })} of ${formatMoney(sizing.sizing_base, { abbreviate: true })}`}
          />
          <StatTile
            label="This position would be"
            value={
              sizing.resulting_weight_pct === null || sizing.resulting_weight_pct === undefined
                ? '—'
                : formatPercent(sizing.resulting_weight_pct)
            }
            detail="Of your portfolio, after buying"
            tone={sizing.exceeds_limit === true ? 'default' : 'muted'}
          />
        </div>

        <Notice tone={sizing.exceeds_limit === true ? 'caution' : 'note'}>
          {sizing.commentary}
        </Notice>
      </CardBody>
    </Card>
  );
}
