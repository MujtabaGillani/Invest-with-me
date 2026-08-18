import {
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  LoadingState,
  Notice,
  PriceChart,
} from '@/components/ui';
import { usePriceHistory } from '@/features/companies/queries';
import { isApiError } from '@/lib/apiClient';
import { formatDate, formatMoney, humanise } from '@/lib/format';
import type { IndicatorReading } from '@/types';

import { useTechnicals } from './queries';

/**
 * Technical readings for one company - guide section 4.
 *
 * The framing note is rendered **first**, above the readings, because that is the
 * guide's actual point: these help with timing, not with what to own, and a
 * bearish reading on a company you intend to hold for years matters far less than
 * a change in its fundamentals. Putting it underneath would make it a footnote.
 *
 * No reading is coloured green or red. An "overbought" RSI is not bad news and a
 * "confirmed" volume reading is not good news - they are observations, and
 * colouring them would turn each into a verdict.
 */
export function TechnicalsPanel({ symbol }: { symbol: string }) {
  const { data: report, isPending, isError, error, refetch } = useTechnicals(symbol);
  const { data: prices } = usePriceHistory(symbol);

  if (isPending) {
    return (
      <Card>
        <LoadingState label="Reading the chart…" />
      </Card>
    );
  }

  if (isError) {
    if (isApiError(error) && error.isInsufficientData) {
      return (
        <Notice tone="note" title="Not enough price history">
          {error.message} Indicators computed from a partial window would look like real readings
          without being any, so none are shown.
        </Notice>
      );
    }
    return (
      <Card>
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Notice title="How to read this">{report.horizon_note}</Notice>

      {prices && prices.bars.length > 1 ? (
        <Card>
          <CardHeader
            title={`Price, last ${prices.sessions} sessions`}
            description={`Closing prices to ${formatDate(report.as_of)}. Latest close ${formatMoney(report.last_close)}.`}
          />
          <CardBody>
            <PriceChart closes={prices.bars.map((bar) => bar.close)} />
            <div className="text-ink-subtle mt-2 flex justify-between text-xs">
              <span>{formatDate(prices.bars[0]?.trade_date)}</span>
              <span>{formatDate(prices.bars[prices.bars.length - 1]?.trade_date)}</span>
            </div>
          </CardBody>
        </Card>
      ) : null}

      <Card>
        <CardHeader
          title="Indicators"
          description={`Computed from ${report.sessions_analysed} stored sessions.`}
        />
        <CardBody className="divide-border divide-y">
          <ReadingRow reading={report.trend} />
          <ReadingRow reading={report.rsi} />
          <ReadingRow reading={report.moving_averages} />
          <ReadingRow reading={report.volume} />
        </CardBody>
      </Card>

      <Notice tone="caution" title="What these cannot do">
        None of the readings above predicts a price. An oversold stock can stay oversold for months,
        and an overbought one can keep climbing. Treat them as one input alongside the fundamentals
        - never as a reason on their own.
      </Notice>
    </div>
  );
}

/**
 * One indicator: its state, its value, and the server's interpretation.
 *
 * The state is rendered as neutral text rather than a coloured badge, for the
 * reason in the module docstring.
 */
function ReadingRow({ reading }: { reading: IndicatorReading }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0 flex-1">
        <p className="text-ink text-sm font-medium">
          {reading.label}
          <span className="text-ink-muted ml-2 font-normal">{humanise(reading.state)}</span>
        </p>
        <p className="text-ink-subtle mt-0.5 text-xs">{reading.what_it_measures}</p>
        <p className="text-ink-muted mt-1 max-w-2xl text-sm">{reading.commentary}</p>
      </div>
      <p className="numeric text-ink shrink-0 text-lg font-semibold">
        {reading.value === null || reading.value === undefined
          ? '—'
          : `${reading.value}${reading.unit ?? ''}`}
      </p>
    </div>
  );
}
