import { useState } from 'react';
import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardBodyFlush,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  StatRow,
  StatTile,
  Table,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
} from '@/components/ui';
import { TradeForm } from '@/features/portfolio/TradeForm';
import { usePortfolio, useTrades } from '@/features/portfolio/queries';
import {
  formatDate,
  formatDateTime,
  formatMoney,
  formatPercent,
  formatQuantity,
} from '@/lib/format';
import type { ConcentrationWarning, Holding, Portfolio, SectorAllocation } from '@/types';

/**
 * The portfolio.
 *
 * Holdings are rebuilt from the trade ledger server-side on every request, so what is
 * shown here can never disagree with the trades that produced it.
 *
 * Two things are given prominence that a conventional portfolio screen would bury:
 * holdings with **no exit rules written down**, and breaches of the user's **own**
 * concentration limits. Both are the guide's points, and both are invisible on a
 * screen that only shows profit and loss.
 */
export function PortfolioPage() {
  const [showTradeForm, setShowTradeForm] = useState(false);
  const { data: portfolio, isPending, isError, error, refetch } = usePortfolio();

  if (isPending) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }

  if (isError) {
    return (
      <Card>
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Card>
    );
  }

  return (
    <>
      <PageHeader
        title="Portfolio"
        description="Positions rebuilt from your recorded trades and valued at the latest close held locally. Not a live quote feed."
        actions={
          <Button variant="primary" onClick={() => setShowTradeForm((open) => !open)}>
            {showTradeForm ? 'Hide trade form' : 'Record a trade'}
          </Button>
        }
      />

      {showTradeForm ? (
        <div className="mb-5">
          <TradeForm />
        </div>
      ) : null}

      {portfolio.holdings.length === 0 ? (
        <Card>
          <EmptyState
            title="No open holdings"
            description="Record a purchase to start tracking. If you already hold shares bought before using this tool, record them with their original date - the cost basis will come out right."
            action={
              <Button variant="primary" onClick={() => setShowTradeForm(true)}>
                Record a trade
              </Button>
            }
          />
        </Card>
      ) : (
        <div className="space-y-5">
          <Summary portfolio={portfolio} />
          {(portfolio.concentration_warnings ?? []).length > 0 ? (
            <ConcentrationCard warnings={portfolio.concentration_warnings ?? []} />
          ) : null}
          <HoldingsTable holdings={portfolio.holdings} />
          <AllocationCard allocations={portfolio.sector_allocations ?? []} />
        </div>
      )}

      <div className="mt-5">
        <TradeLedger />
      </div>
    </>
  );
}

function Summary({ portfolio }: { portfolio: Portfolio }) {
  const { summary } = portfolio;

  return (
    <>
      <StatRow>
        <StatTile
          label="Market value"
          value={formatMoney(summary.total_market_value, { abbreviate: true })}
          detail={
            portfolio.valued_at ? `Valued ${formatDateTime(portfolio.valued_at)}` : 'Not yet valued'
          }
        />
        <StatTile
          label="Unrealised"
          value={formatMoney(summary.total_unrealised_pl, { abbreviate: true })}
          detail={formatPercent(summary.total_unrealised_pl_pct, { signed: true })}
          tone="signed"
          signedFrom={summary.total_unrealised_pl}
        />
        <StatTile
          label="Realised"
          value={formatMoney(summary.total_realised_pl, { abbreviate: true })}
          detail={`After ${formatMoney(summary.total_fees_paid)} of fees`}
          tone="signed"
          signedFrom={summary.total_realised_pl}
        />
        <StatTile
          label="Spread across"
          value={`${summary.holdings_count} holding${summary.holdings_count === 1 ? '' : 's'}`}
          detail={`${summary.sectors_held} sector${summary.sectors_held === 1 ? '' : 's'}`}
        />
      </StatRow>

      <Notice
        tone={(summary.holdings_without_exit_rules ?? 0) > 0 ? 'caution' : 'note'}
        title={
          (summary.holdings_without_exit_rules ?? 0) > 0
            ? `${summary.holdings_without_exit_rules} holding${summary.holdings_without_exit_rules === 1 ? '' : 's'} with no exit rules`
            : 'Diversification'
        }
      >
        {(summary.holdings_without_exit_rules ?? 0) > 0 ? (
          <>
            You are holding {summary.holdings_without_exit_rules === 1 ? 'a position' : 'positions'}{' '}
            with no profit target or stop-loss written down. Deciding those now, while you are not
            watching the price move, is the whole point of setting them in advance.{' '}
            <Link to="/plans" className="text-accent underline">
              Open a plan
            </Link>
            . {summary.diversification_note}
          </>
        ) : (
          summary.diversification_note
        )}
      </Notice>
    </>
  );
}

function ConcentrationCard({ warnings }: { warnings: ConcentrationWarning[] }) {
  return (
    <Card>
      <CardHeader
        title="Above your own limits"
        description="Measured against the caps you set in your investor profile, not against any external standard."
      />
      <CardBody className="space-y-2">
        {warnings.map((warning) => (
          <div
            key={`${warning.kind}-${warning.subject}`}
            className="border-severity-warning bg-surface-sunken rounded-md border-l-2 px-3 py-2"
          >
            <p className="text-ink text-sm">{warning.message}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

/**
 * Holdings, largest first.
 *
 * The stop-loss and profit-target columns show the *price* each rule resolves to, not
 * the percentage - because that is the number the user can compare against the last
 * close without doing arithmetic.
 */
function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  return (
    <Card>
      <CardHeader
        title="Holdings"
        description="Cost basis is the weighted average of what you paid, including buy-side fees."
      />
      <CardBodyFlush>
        <Table>
          <THead>
            <TR>
              <TH>Company</TH>
              <TH numeric>Shares</TH>
              <TH numeric>Average cost</TH>
              <TH numeric>Last close</TH>
              <TH numeric>Value</TH>
              <TH numeric>Unrealised</TH>
              <TH numeric>Weight</TH>
              <TH>Your exit rules</TH>
            </TR>
          </THead>
          <TBody>
            {holdings.map((holding) => (
              <TR key={holding.company_id}>
                <THRow>
                  <Link
                    to={`/companies/${holding.symbol}`}
                    className="text-accent font-semibold hover:underline"
                  >
                    {holding.symbol}
                  </Link>
                  <span className="text-ink-subtle ml-2 text-xs font-normal">
                    {holding.sector_label}
                  </span>
                </THRow>
                <TD numeric>{formatQuantity(holding.quantity)}</TD>
                <TD numeric>{formatMoney(holding.average_cost)}</TD>
                <TD numeric>
                  {formatMoney(holding.last_price)}
                  <span className="text-ink-subtle ml-1.5 text-xs">
                    {formatDate(holding.last_price_date)}
                  </span>
                </TD>
                <TD numeric>{formatMoney(holding.market_value, { abbreviate: true })}</TD>
                <TD
                  numeric
                  className={
                    (holding.unrealised_pl ?? '').startsWith('-') ? 'text-loss' : 'text-gain'
                  }
                >
                  {formatMoney(holding.unrealised_pl, { abbreviate: true })}
                  <span className="ml-1.5 text-xs">
                    {formatPercent(holding.unrealised_pl_pct, { signed: true })}
                  </span>
                </TD>
                <TD numeric>{formatPercent(holding.weight_pct, { decimals: 1 })}</TD>
                <TD>
                  {holding.missing_exit_rules ? (
                    <Badge
                      className="bg-verdict-weak-bg text-verdict-weak"
                      title="No profit target or stop-loss was written down for this position."
                    >
                      None set
                    </Badge>
                  ) : (
                    <div className="numeric text-xs">
                      <p className="text-ink-muted">
                        Target {formatMoney(holding.profit_target_price)}{' '}
                        <span className="text-ink-subtle">
                          ({formatPercent(holding.distance_to_target_pct, { signed: true })} away)
                        </span>
                      </p>
                      <p className="text-ink-muted">
                        Stop {formatMoney(holding.stop_loss_price)}{' '}
                        <span className="text-ink-subtle">
                          ({formatPercent(holding.distance_to_stop_pct)} below)
                        </span>
                      </p>
                      {holding.plan_id ? (
                        <Link
                          to={`/plans/${holding.plan_id}`}
                          className="text-accent hover:underline"
                        >
                          View plan
                        </Link>
                      ) : null}
                    </div>
                  )}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardBodyFlush>
    </Card>
  );
}

function AllocationCard({ allocations }: { allocations: SectorAllocation[] }) {
  const largest = Math.max(...allocations.map((item) => Number(item.weight_pct) || 0), 1);

  return (
    <Card>
      <CardHeader
        title="Sector allocation"
        description="Diversifying across sectors limits the damage any one of them can do."
      />
      <CardBody className="space-y-3">
        {allocations.map((allocation) => (
          <div key={allocation.sector}>
            <div className="mb-1 flex items-baseline justify-between text-sm">
              <span className="text-ink">
                {allocation.sector_label}
                <span className="text-ink-subtle ml-2 text-xs">
                  {allocation.holdings_count} holding
                  {allocation.holdings_count === 1 ? '' : 's'}
                </span>
              </span>
              <span className="numeric text-ink-muted">
                {formatPercent(allocation.weight_pct, { decimals: 1 })}
                <span className="text-ink-subtle ml-2">
                  {formatMoney(allocation.market_value, { abbreviate: true })}
                </span>
              </span>
            </div>
            {/* A bar rather than a pie: comparing lengths is easier than comparing
                angles, and this is fundamentally a ranked comparison. */}
            <div className="bg-surface-sunken h-2 overflow-hidden rounded-full">
              <div
                className={
                  allocation.exceeds_limit ? 'bg-severity-warning h-full' : 'bg-accent h-full'
                }
                style={{ width: `${((Number(allocation.weight_pct) || 0) / largest) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}

/** The trade ledger - the append-only record everything above is derived from. */
function TradeLedger() {
  const { data: trades, isPending, isError, error, refetch } = useTrades();

  return (
    <Card>
      <CardHeader
        title="Trade ledger"
        description="Every trade you have recorded, newest first. Your holdings are recomputed from this list on every request."
      />
      {isError ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : isPending ? (
        <LoadingState />
      ) : trades.length === 0 ? (
        <EmptyState title="No trades recorded yet" />
      ) : (
        <CardBodyFlush>
          <Table>
            <THead>
              <TR>
                <TH>Date</TH>
                <TH>Company</TH>
                <TH>Side</TH>
                <TH numeric>Shares</TH>
                <TH numeric>Price</TH>
                <TH numeric>Fees</TH>
                <TH numeric>Cash effect</TH>
                <TH>Note</TH>
              </TR>
            </THead>
            <TBody>
              {trades.map((trade) => (
                <TR key={trade.id}>
                  <TD>{formatDate(trade.executed_at)}</TD>
                  <THRow>{trade.symbol}</THRow>
                  <TD>
                    <Badge
                      className={
                        trade.side === 'buy'
                          ? 'bg-verdict-adequate-bg text-verdict-adequate'
                          : 'bg-surface-sunken text-ink-muted'
                      }
                    >
                      {trade.side === 'buy' ? 'Bought' : 'Sold'}
                    </Badge>
                  </TD>
                  <TD numeric>{formatQuantity(trade.quantity)}</TD>
                  <TD numeric>{formatMoney(trade.price)}</TD>
                  <TD numeric>{formatMoney(trade.fees)}</TD>
                  <TD numeric>{formatMoney(trade.net_cash_flow)}</TD>
                  <TD className="text-ink-subtle max-w-xs text-xs">{trade.note}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </CardBodyFlush>
      )}
    </Card>
  );
}
