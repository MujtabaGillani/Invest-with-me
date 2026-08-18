import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingState,
  ProfitChart,
  StatTile,
  Table,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
} from '@/components/ui';
import { usePortfolio } from '@/features/portfolio/queries';
import { usePortfolioHistory, useSellReview } from '@/features/screener/queries';
import { formatDate, formatMoney, formatPercent } from '@/lib/format';

/**
 * Your money: what you put in, what it is worth, and what you hold.
 *
 * The simplified replacement for the dashboard and portfolio screens. Answers four
 * questions in order: how much have I invested, how much is it worth, is anything
 * demanding a decision, and what exactly do I own.
 *
 * Every figure here is a **fact** rather than an estimate - it is derived from the
 * user's own trade ledger and the stored closing prices, which is why this page can
 * be blunt where the buy/sell page has to be careful. The one caveat it does carry is
 * the price delay, since a valuation is only as current as the last close behind it.
 */

export function MoneyPage() {
  const history = usePortfolioHistory();
  const portfolio = usePortfolio();
  const sell = useSellReview();

  const needsAttention = sell.data?.items.filter((item) => item.urgency === 'act_now').length ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Your money"
        description="What you have put in, what it is worth now, and what you own."
      />

      {history.isPending ? (
        <LoadingState label="Adding up your trades" />
      ) : history.isError ? (
        <ErrorState error={history.error} />
      ) : history.data.first_trade_on === null ? (
        <Card>
          <EmptyState
            title="You have not recorded any trades yet"
            description="Once you record a purchase, this page shows what you invested, what it is worth, and how that has moved over time."
            action={
              <Link to="/" className="text-accent text-sm underline">
                See what passes the checks
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile
              label="Invested"
              value={formatMoney(history.data.total_invested)}
              detail={`Since ${formatDate(history.data.first_trade_on)}`}
            />
            <StatTile
              label="Worth now"
              value={formatMoney(history.data.total_market_value)}
              detail={
                portfolio.data
                  ? `${portfolio.data.summary.holdings_count} holdings`
                  : 'Latest stored close'
              }
            />
            <StatTile
              label="Profit"
              value={formatMoney(history.data.total_profit)}
              detail={
                history.data.total_profit_pct === null
                  ? 'Nothing currently invested'
                  : `${formatPercent(history.data.total_profit_pct)} on what you paid`
              }
              tone="signed"
              signedFrom={history.data.total_profit}
            />
            <StatTile
              label="Banked"
              value={formatMoney(history.data.realised_profit)}
              detail="Profit already taken on shares sold"
              tone="signed"
              signedFrom={history.data.realised_profit}
            />
          </div>

          {needsAttention > 0 ? (
            <Card>
              <CardBody>
                <p className="text-ink text-sm">
                  {needsAttention === 1
                    ? 'One holding has crossed a rule you set.'
                    : `${needsAttention} holdings have crossed rules you set.`}{' '}
                  <Link to="/" className="text-accent underline">
                    See what and why
                  </Link>
                </p>
              </CardBody>
            </Card>
          ) : null}

          <Card>
            <CardHeader
              title="Profit and loss over time"
              description="The solid line is what your holdings are worth. The dashed line is what you paid. The gap between them is your profit or loss."
            />
            <CardBody>
              <ProfitChart
                invested={history.data.points.map((point) => point.invested)}
                marketValue={history.data.points.map((point) => point.market_value)}
              />
              <div className="text-ink-muted mt-2 flex justify-between text-xs">
                <span>{formatDate(history.data.points[0]?.on_date)}</span>
                <span>
                  {formatDate(history.data.points[history.data.points.length - 1]?.on_date)}
                </span>
              </div>
              <p className="text-ink-subtle mt-3 text-xs">{history.data.note}</p>
            </CardBody>
          </Card>
        </>
      )}

      <Card>
        <CardHeader title="What you own" />
        {portfolio.isPending ? (
          <LoadingState label="Rebuilding your holdings" />
        ) : portfolio.isError ? (
          <ErrorState error={portfolio.error} />
        ) : portfolio.data.holdings.length === 0 ? (
          <EmptyState title="Nothing held right now" />
        ) : (
          <Table>
            <THead>
              <THRow>
                <TH>Company</TH>
                <TH numeric>Shares</TH>
                <TH numeric>You paid</TH>
                <TH numeric>Worth now</TH>
                <TH numeric>Profit</TH>
              </THRow>
            </THead>
            <TBody>
              {portfolio.data.holdings.map((holding) => (
                <TR key={holding.symbol}>
                  <TD>
                    <Link to={`/companies/${holding.symbol}`} className="text-accent font-medium">
                      {holding.symbol}
                    </Link>
                    <span className="text-ink-muted ml-2 text-xs">{holding.sector_label}</span>
                  </TD>
                  <TD numeric>{holding.quantity}</TD>
                  <TD numeric>{formatMoney(holding.cost_basis)}</TD>
                  <TD numeric>{formatMoney(holding.market_value)}</TD>
                  <TD numeric>
                    {formatMoney(holding.unrealised_pl)}
                    <span className="text-ink-muted ml-1 text-xs">
                      {formatPercent(holding.unrealised_pl_pct)}
                    </span>
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
