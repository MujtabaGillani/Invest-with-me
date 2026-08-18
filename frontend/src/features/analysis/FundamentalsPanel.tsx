import {
  Card,
  CardBody,
  CardBodyFlush,
  CardHeader,
  ErrorState,
  LoadingState,
  Notice,
  Sparkline,
  StatRow,
  StatTile,
  Table,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
  VerdictBadge,
} from '@/components/ui';
import { isApiError } from '@/lib/apiClient';
import { formatDate, formatMetricValue, formatMoney } from '@/lib/format';
import type { FundamentalsReport, RedFlag, StatementReview } from '@/types';

import { useFundamentals } from './queries';

/**
 * The fundamentals checklist for one company - guide sections 2 and 3.
 *
 * Everything rendered here comes from the server: the verdict, the criteria, and
 * the sentence explaining how this company reads against them. The frontend adds
 * no interpretation of its own, which is what keeps the wording consistent with
 * the thresholds that were actually applied.
 *
 * Note the absence of an overall grade. The score is a count of criteria met, and
 * that is deliberate - a single number would invite ranking companies by it.
 */
export function FundamentalsPanel({ symbol }: { symbol: string }) {
  const { data: report, isPending, isError, error, refetch } = useFundamentals(symbol);

  if (isPending) {
    return (
      <Card>
        <LoadingState label="Running the checklist…" />
      </Card>
    );
  }

  if (isError) {
    // "No filings loaded" is a normal state, not a failure - the server says so
    // with a specific code, and it gets a plain explanation rather than an alarm.
    if (isApiError(error) && error.isInsufficientData) {
      return (
        <Notice tone="note" title="Not enough data for the checklist">
          {error.message} You can still read the price history, and the raw statements if any have
          been loaded.
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
      <ScoreSummary report={report} />
      <MetricsTable report={report} />
      <StatementReviewCard review={report.statement_review} />
      {report.red_flags.length > 0 ? <RedFlagsCard flags={report.red_flags} /> : null}
    </div>
  );
}

function ScoreSummary({ report }: { report: FundamentalsReport }) {
  const { score } = report;

  return (
    <>
      <StatRow>
        <StatTile
          label="Criteria met"
          value={`${score.strong + score.adequate} of ${score.metrics_assessed}`}
          detail={`${score.strong} strong, ${score.adequate} adequate`}
        />
        <StatTile
          label="Fall short"
          value={score.weak}
          detail={score.weak === 0 ? 'None' : 'Worth understanding why'}
          tone={score.weak > 0 ? 'default' : 'muted'}
        />
        <StatTile
          label="Cannot judge"
          value={score.insufficient_data}
          detail="Not the same as a bad result"
          tone="muted"
        />
        <StatTile
          label="Valued at"
          value={formatMoney(report.reference_price)}
          detail={formatDate(report.reference_price_date)}
        />
      </StatRow>

      <Notice title="What this is">
        {score.note} Figures cover fiscal years {report.fiscal_years[0]}–{report.latest_fiscal_year}
        {report.peer_count > 0
          ? `, with valuation and gearing compared against ${report.peer_count} ${report.sector_label} peer${report.peer_count === 1 ? '' : 's'}.`
          : `. No sector peers with usable figures were found, so valuation is judged against general bands rather than against ${report.sector_label} companies.`}
      </Notice>
    </>
  );
}

function MetricsTable({ report }: { report: FundamentalsReport }) {
  return (
    <Card>
      <CardHeader
        title="The fundamentals checklist"
        description="Each row states what the metric tells you, what a good reading looks like, and how this company compares."
      />
      <CardBodyFlush>
        <Table>
          <THead>
            <TR>
              <TH>Metric</TH>
              <TH numeric>Value</TH>
              <TH numeric>Peer median</TH>
              <TH>Trend</TH>
              <TH>Reading</TH>
            </TR>
          </THead>
          <TBody>
            {report.metrics.map((metric) => (
              <TR key={metric.key}>
                <THRow className="align-top">
                  <div className="max-w-xs">
                    <p>{metric.label}</p>
                    {/* The guide's middle column: what the metric tells you. */}
                    <p className="text-ink-subtle mt-0.5 text-xs font-normal">
                      {metric.what_it_measures}
                    </p>
                  </div>
                </THRow>
                <TD numeric className="align-top">
                  {formatMetricValue(metric.value, metric.unit)}
                </TD>
                <TD numeric className="text-ink-muted align-top">
                  {metric.peer_median === null || metric.peer_median === undefined
                    ? '—'
                    : formatMetricValue(metric.peer_median, metric.unit)}
                </TD>
                <TD className="align-top">
                  <Sparkline values={(metric.history ?? []).map((point) => point.value)} />
                </TD>
                <TD className="align-top">
                  <div className="max-w-md space-y-1.5">
                    <VerdictBadge verdict={metric.verdict} />
                    {/* The server's own commentary. Never re-worded client-side. */}
                    <p className="text-ink-muted text-xs">{metric.commentary}</p>
                    <p className="text-ink-subtle text-xs italic">Looking for: {metric.criteria}</p>
                  </div>
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardBodyFlush>
    </Card>
  );
}

function StatementReviewCard({ review }: { review: StatementReview }) {
  return (
    <Card>
      <CardHeader
        title="The three statements, in plain terms"
        description="Four questions across the income statement, balance sheet and cash flow statement."
      />
      <CardBody className="space-y-3">
        {review.checks.map((check) => (
          <div key={check.key} className="border-border flex gap-3 border-l-2 pl-3">
            <span
              aria-hidden="true"
              className={
                check.passed === true
                  ? 'text-verdict-strong'
                  : check.passed === false
                    ? 'text-verdict-weak'
                    : 'text-ink-subtle'
              }
            >
              {check.passed === true ? '✓' : check.passed === false ? '✕' : '?'}
            </span>
            <div className="min-w-0">
              <p className="text-ink text-sm">
                {check.question}{' '}
                <span className="font-medium">
                  {check.passed === true
                    ? 'Yes'
                    : check.passed === false
                      ? 'No'
                      : 'Cannot tell from the data'}
                </span>
              </p>
              <p className="text-ink-muted mt-0.5 text-xs">{check.detail}</p>
            </div>
          </div>
        ))}

        <Notice tone={review.needs_investigation ? 'caution' : 'note'}>{review.summary}</Notice>
      </CardBody>
    </Card>
  );
}

function RedFlagsCard({ flags }: { flags: RedFlag[] }) {
  return (
    <Card>
      <CardHeader
        title="Worth investigating"
        description="Specific observations from the reported figures - each names the evidence, so you can go and check the filing."
      />
      <CardBody className="space-y-3">
        {flags.map((flag) => (
          <div
            key={flag.key}
            className={
              flag.severity === 'critical'
                ? 'border-verdict-weak bg-verdict-weak-bg rounded-md border-l-2 px-3 py-2'
                : 'border-severity-warning bg-surface-sunken rounded-md border-l-2 px-3 py-2'
            }
          >
            <p className="text-ink text-sm font-medium">{flag.title}</p>
            <p className="text-ink-muted mt-1 text-sm">{flag.detail}</p>
          </div>
        ))}
      </CardBody>
    </Card>
  );
}
