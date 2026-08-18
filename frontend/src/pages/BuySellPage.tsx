import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Badge,
  Card,
  CardBody,
  CardHeader,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
} from '@/components/ui';
import { useBuyCandidates, useSellReview } from '@/features/screener/queries';
import { formatMoney, formatPercent } from '@/lib/format';
import type { BuyCandidate, SellReviewItem } from '@/types';

/**
 * Buy and sell, on one screen.
 *
 * The simplified answer to "what should I buy, and what should I sell". Two lists,
 * sell first, because a decision about money already at risk matters more than a
 * decision about money that is not.
 *
 * **What this page is careful never to say.** It does not say a company will go up,
 * that a purchase will be profitable, or that anything is a "buy". The buy list is
 * ordered by how many of the seven checks each company currently passes against its
 * published accounts, and every row shows the reasons and the gaps so the ranking can
 * be argued with. The sell list contains only the user's own rules, quoted back to
 * them. Those two framings are what make the page honest, and they are also what
 * makes it useful - a list of unexplained tickers would be neither.
 */

/** The sell-side reasons, in the words of someone who is not a trader. */
const SELL_REASON_LABEL: Record<string, string> = {
  profit_target_reached: 'Your profit target was reached',
  stop_loss_breached: 'Your stop-loss was passed',
  review_due: 'Time to re-check why you bought it',
  no_exit_rules: 'No sell plan yet',
  position_too_large: 'This has grown too big a share of your money',
};

function CheckPips({ passed, total }: { passed: number; total: number }) {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      {Array.from({ length: total }, (_unused, index) => (
        <span
          key={index}
          className={`h-2 w-2 rounded-full ${index < passed ? 'bg-verdict-strong' : 'bg-border'}`}
        />
      ))}
    </span>
  );
}

function BuyRow({ candidate }: { candidate: BuyCandidate }) {
  const suggested = candidate.suggested;
  // These carry server-side defaults, so the generated types mark them optional.
  const why = candidate.why ?? [];
  const watchOutFor = candidate.watch_out_for ?? [];
  return (
    <li className="border-border border-b p-4 last:border-b-0 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <Link to={`/companies/${candidate.symbol}`} className="text-accent font-semibold">
            {candidate.symbol}
          </Link>
          <span className="text-ink-muted text-sm">{candidate.company_name}</span>
          {candidate.already_owned ? <Badge>You own this</Badge> : null}
        </div>
        <div className="flex items-baseline gap-2 text-sm">
          <CheckPips passed={candidate.checks_passed} total={candidate.checks_total} />
          <span className="text-ink-muted">
            passes {candidate.checks_passed} of {candidate.checks_total} checks
          </span>
        </div>
      </div>

      <p className="text-ink-subtle mt-1 text-xs">
        {candidate.sector_label} · {formatMoney(candidate.last_price)}
      </p>

      {why.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm">
          {why.map((reason) => (
            <li key={reason} className="text-ink">
              <span className="text-verdict-strong" aria-hidden="true">
                ✓{' '}
              </span>
              {reason}
            </li>
          ))}
        </ul>
      ) : null}

      {watchOutFor.length > 0 ? (
        <ul className="mt-2 space-y-1 text-sm">
          {watchOutFor.map((warning) => (
            <li key={warning} className="text-ink-muted">
              <span aria-hidden="true">! </span>
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {candidate.timing_note ? (
        <p className="text-ink-muted mt-2 text-sm">{candidate.timing_note}</p>
      ) : null}

      {suggested ? (
        <div className="bg-surface-sunken mt-3 rounded-md p-3 text-sm">
          <p className="text-ink">
            <span className="font-medium">If you buy:</span>{' '}
            {suggested.suggested_amount === null ? (
              <>
                set how much you have to invest on{' '}
                <Link to="/profile" className="text-accent underline">
                  your plan
                </Link>{' '}
                and a size will appear here.
              </>
            ) : (
              <>
                up to {formatMoney(suggested.suggested_amount)}
                {suggested.suggested_shares === null
                  ? null
                  : ` (about ${suggested.suggested_shares} shares)`}
                . Sell at {formatMoney(suggested.profit_target_price)} for a{' '}
                {formatPercent(suggested.profit_target_pct)} gain, or cut it at{' '}
                {formatMoney(suggested.stop_loss_price)} to cap the loss at{' '}
                {formatPercent(suggested.stop_loss_pct)}.
              </>
            )}
          </p>
          <p className="text-ink-subtle mt-1 text-xs">{suggested.basis}</p>
        </div>
      ) : null}
    </li>
  );
}

function SellRow({ item }: { item: SellReviewItem }) {
  const urgent = item.urgency === 'act_now';
  return (
    <li className="border-border border-b p-4 last:border-b-0 sm:p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <Link to={`/companies/${item.symbol}`} className="text-accent font-semibold">
            {item.symbol}
          </Link>
          <span className="text-ink-muted text-sm">{item.company_name}</span>
        </div>
        <Badge className={urgent ? 'bg-verdict-weak-bg text-verdict-weak' : undefined}>
          {SELL_REASON_LABEL[item.reason] ?? item.reason}
        </Badge>
      </div>

      <p className="text-ink mt-2 text-sm">{item.headline}</p>

      {item.what_you_said ? (
        <p className="text-ink-subtle mt-1 text-xs italic">
          Your rule: &ldquo;{item.what_you_said}&rdquo;
        </p>
      ) : null}

      <p className="text-ink-muted mt-2 text-xs">
        {formatMoney(item.last_price)} now · you paid {formatMoney(item.average_cost)} ·{' '}
        {formatPercent(item.unrealised_pl_pct)}
      </p>
    </li>
  );
}

export function BuySellPage() {
  const buy = useBuyCandidates(10);
  const sell = useSellReview();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Buy and sell"
        description="What passes the checks, and what you already own that has crossed a line you drew."
      />

      {/* Sell first: money already at risk outranks money that is not. */}
      <Card>
        <CardHeader
          title="Sell or review"
          description="Only your own rules. The app does not decide this for you."
        />
        {sell.isPending ? (
          <LoadingState label="Checking your holdings" />
        ) : sell.isError ? (
          <ErrorState error={sell.error} />
        ) : sell.data.items.length === 0 ? (
          <EmptyState
            title="Nothing to act on"
            description={
              sell.data.holdings_count === 0
                ? 'You do not own anything yet.'
                : 'None of your holdings has reached a profit target, breached a stop-loss, or grown past your limits.'
            }
          />
        ) : (
          <ul>
            {sell.data.items.map((item) => (
              <SellRow key={`${item.symbol}-${item.reason}`} item={item} />
            ))}
          </ul>
        )}
      </Card>

      <Card>
        <CardHeader
          title="Worth a look"
          description="Ranked by how many checks each company passes right now — not by what it might do next."
        />
        {buy.isPending ? (
          <LoadingState label="Checking companies" />
        ) : buy.isError ? (
          <ErrorState error={buy.error} />
        ) : (
          <>
            <CardBody>
              <Notice tone="note">
                No tool can tell you which shares will be profitable, and this one does not try.
                These are the companies whose published accounts currently meet the most criteria,
                with the reasons and the gaps shown so you can disagree.
                {(buy.data.unavailable_checks ?? []).length > 0 ? (
                  <>
                    {' '}
                    Your data source does not publish{' '}
                    {(buy.data.unavailable_checks ?? []).join(', ')}, so those checks could not be
                    run for any company.
                  </>
                ) : null}
              </Notice>
            </CardBody>
            {buy.data.candidates.length === 0 ? (
              <EmptyState
                title="No company passed enough checks"
                description={`Assessed ${buy.data.companies_scanned} companies. This is a real answer, not an empty screen — with limited published data, few companies clear the bar.`}
              />
            ) : (
              <ul>
                {buy.data.candidates.map((candidate) => (
                  <BuyRow key={candidate.symbol} candidate={candidate} />
                ))}
              </ul>
            )}
            <CardBody>
              <p className="text-ink-subtle text-xs">
                Assessed {buy.data.companies_scanned} companies
                {buy.data.companies_skipped > 0
                  ? `; ${buy.data.companies_skipped} had too little stored data to judge`
                  : ''}
                .{' '}
                {buy.data.price_delay_minutes === null || buy.data.price_delay_minutes === 0
                  ? ''
                  : `Prices are at least ${buy.data.price_delay_minutes} minutes old.`}
              </p>
            </CardBody>
          </>
        )}
      </Card>
    </div>
  );
}
