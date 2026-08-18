import { useState } from 'react';
import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  AnswerBadge,
  Button,
  Card,
  CardBodyFlush,
  CardFooter,
  EmptyState,
  ErrorState,
  Notice,
  PlanStatusBadge,
  SelectField,
  Table,
  TableSkeleton,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
} from '@/components/ui';
import { PLANS_PAGE_SIZE, usePlans } from '@/features/plans/queries';
import { formatMoney, formatPercent } from '@/lib/format';

/**
 * The list of trade plans.
 *
 * The checklist progress is shown per row as five markers rather than "3/5",
 * because which questions are unanswered matters more than how many - and the
 * distinction between unanswered and answered-no has to survive into the summary.
 */

const STATUS_OPTIONS = [
  { value: 'draft', label: 'Draft — still being worked through' },
  { value: 'ready', label: 'Committed — not yet acted on' },
  { value: 'executed', label: 'Executed — governing a real position' },
  { value: 'abandoned', label: 'Abandoned — decided against' },
  { value: 'closed', label: 'Closed — position exited' },
];

export function PlansPage() {
  const [status, setStatus] = useState('');
  const [offset, setOffset] = useState(0);

  const { data, isPending, isError, error, refetch } = usePlans({
    status: status || undefined,
    offset,
  });

  const total = data?.total ?? 0;
  const shown = data?.items.length ?? 0;
  const hasMore = offset + shown < total;

  return (
    <>
      <PageHeader
        title="Trade plans"
        description="A plan is what you decide before buying: whether the business passes the checklist, how much to put in, and at what point you would take profit or cut a loss. Start one from any company page."
      />

      <Notice title="Why decide the exit first">
        Once you own something, every judgement about when to sell competes with hope and with the
        price on the screen. A plan is the version of that decision you made while neither applied.
      </Notice>

      <Card className="mt-5">
        <div className="border-border max-w-sm border-b px-5 py-4">
          <SelectField
            label="Status"
            options={STATUS_OPTIONS}
            value={status}
            placeholder="All plans"
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          />
        </div>

        {isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : isPending ? (
          <TableSkeleton columns={5} />
        ) : data.items.length === 0 ? (
          <EmptyState
            title={status ? 'No plans with that status' : 'No plans yet'}
            description={
              status
                ? 'Try clearing the filter.'
                : 'Find a company you are interested in and start a plan from its page. You can work through the checklist over several sittings.'
            }
            action={
              <Link to="/companies" className="text-accent text-sm font-medium hover:underline">
                Browse companies
              </Link>
            }
          />
        ) : (
          <>
            <CardBodyFlush>
              <Table>
                <THead>
                  <TR>
                    <TH>Company</TH>
                    <TH>Status</TH>
                    <TH>Checklist</TH>
                    <TH numeric>Intended</TH>
                    <TH numeric>Target / stop</TH>
                    <TH>Outstanding</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((plan) => (
                    <TR key={plan.id}>
                      <THRow>
                        <Link
                          to={`/plans/${plan.id}`}
                          className="text-accent font-semibold hover:underline"
                        >
                          {plan.symbol}
                        </Link>
                        <span className="text-ink-subtle ml-2 text-xs font-normal">
                          {plan.company_name}
                        </span>
                      </THRow>
                      <TD>
                        <PlanStatusBadge status={plan.status} />
                      </TD>
                      <TD>
                        <div className="flex gap-1">
                          {plan.checklist.map((item) => (
                            <span
                              key={item.key}
                              title={`${item.question} — ${
                                item.answer === true
                                  ? 'Yes'
                                  : item.answer === false
                                    ? 'No'
                                    : 'Not yet answered'
                              }`}
                              className={
                                item.answer === true
                                  ? 'bg-verdict-strong size-2.5 rounded-full'
                                  : item.answer === false
                                    ? 'bg-verdict-weak size-2.5 rounded-full'
                                    : 'bg-border-strong size-2.5 rounded-full'
                              }
                            />
                          ))}
                        </div>
                      </TD>
                      <TD numeric>{formatMoney(plan.intended_amount, { abbreviate: true })}</TD>
                      <TD numeric>
                        {plan.profit_target_pct && plan.stop_loss_pct ? (
                          <>
                            {formatPercent(plan.profit_target_pct, { decimals: 0 })} /{' '}
                            {formatPercent(plan.stop_loss_pct, { decimals: 0 })}
                          </>
                        ) : (
                          <span className="text-verdict-weak text-xs">Not set</span>
                        )}
                      </TD>
                      <TD>
                        {plan.readiness.can_commit ? (
                          <span className="text-ink-subtle text-xs">Nothing</span>
                        ) : (
                          <span className="text-ink-muted text-xs">
                            {(plan.readiness.blocking_reasons ?? []).length} to settle
                          </span>
                        )}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
            </CardBodyFlush>

            <CardFooter className="flex items-center justify-between">
              <p className="text-ink-muted numeric text-xs">
                Showing {offset + 1}–{offset + shown} of {total}
              </p>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PLANS_PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  disabled={!hasMore}
                  onClick={() => setOffset(offset + PLANS_PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </CardFooter>
          </>
        )}
      </Card>

      {/* Referenced so the import is used and the legend explains the markers. */}
      <p className="text-ink-subtle mt-3 flex items-center gap-2 text-xs">
        Checklist markers: <AnswerBadge answer={true} /> <AnswerBadge answer={false} />{' '}
        <AnswerBadge answer={null} />
      </p>
    </>
  );
}
