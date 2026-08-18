import { Link, useParams, useSearchParams } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Badge,
  Button,
  Card,
  CardBody,
  CardBodyFlush,
  CardHeader,
  ErrorState,
  LoadingState,
  Notice,
  StatRow,
  StatTile,
  TabPanel,
  Table,
  Tabs,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
  type TabDefinition,
} from '@/components/ui';
import { FundamentalsPanel } from '@/features/analysis/FundamentalsPanel';
import { TechnicalsPanel } from '@/features/analysis/TechnicalsPanel';
import { useCompany } from '@/features/companies/queries';
import { useCreatePlan } from '@/features/plans/queries';
import { isApiError } from '@/lib/apiClient';
import { formatDate, formatMoney } from '@/lib/format';
import type { AnnualFinancials, CompanyDetail } from '@/types';

/**
 * One company: reference data, the fundamentals checklist, technical readings and
 * the raw statements.
 *
 * The selected tab lives in the URL (`?view=technicals`) so a link can point at a
 * specific view, and the browser's back button steps between tabs the way a user
 * expects.
 *
 * Tab order encodes the guide's advice: fundamentals first, because technicals are
 * only useful "once you've confirmed a company is fundamentally sound". A tab whose
 * data is missing is disabled with the reason in its tooltip, rather than leading to
 * an error.
 */

type View = 'fundamentals' | 'technicals' | 'statements';

export function CompanyPage() {
  const { symbol = '' } = useParams<{ symbol: string }>();
  const [searchParams, setSearchParams] = useSearchParams();

  const { data: company, isPending, isError, error, refetch } = useCompany(symbol);

  const requested = searchParams.get('view');
  const view: View =
    requested === 'technicals' || requested === 'statements' ? requested : 'fundamentals';

  function setView(next: View) {
    const params = new URLSearchParams(searchParams);
    if (next === 'fundamentals') params.delete('view');
    else params.set('view', next);
    setSearchParams(params, { replace: true });
  }

  if (isPending) {
    return (
      <Card>
        <LoadingState />
      </Card>
    );
  }

  if (isError) {
    if (isApiError(error) && error.isNotFound) {
      return (
        <Card>
          <CardBody>
            <p className="text-ink text-sm font-medium">No company with symbol “{symbol}”</p>
            <p className="text-ink-muted mt-1 text-sm">
              Check the ticker, or{' '}
              <Link to="/companies" className="text-accent hover:underline">
                browse the full list
              </Link>
              .
            </p>
          </CardBody>
        </Card>
      );
    }
    return (
      <Card>
        <ErrorState error={error} onRetry={() => void refetch()} />
      </Card>
    );
  }

  const tabs: TabDefinition<View>[] = [
    {
      id: 'fundamentals',
      label: 'Fundamentals',
      disabled: !company.has_financials,
      disabledReason: 'No financial statements are loaded for this company.',
    },
    {
      id: 'technicals',
      label: 'Technicals',
      disabled: !company.has_price_history,
      disabledReason: 'No price history is loaded for this company.',
    },
    { id: 'statements', label: 'Reported figures', disabled: !company.has_financials },
  ];

  return (
    <>
      <PageHeader
        title={`${company.symbol} · ${company.name}`}
        description={company.business_summary}
        actions={<StartPlanButton company={company} />}
      />

      <div className="mb-5">
        <StatRow>
          <StatTile
            label="Latest close"
            value={formatMoney(company.last_close)}
            detail={formatDate(company.last_close_date)}
          />
          <StatTile label="Sector" value={company.sector_label} detail="Used for peer comparison" />
          <StatTile
            label="Years reported"
            value={company.fiscal_years?.length ?? 0}
            detail={
              company.fiscal_years && company.fiscal_years.length > 0
                ? `${company.fiscal_years[0]}–${company.fiscal_years[company.fiscal_years.length - 1]}`
                : 'None loaded'
            }
          />
          <StatTile
            label="Verify yourself"
            value={
              company.website ? (
                <a
                  href={company.website}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-accent text-base hover:underline"
                >
                  Investor relations
                </a>
              ) : (
                '—'
              )
            }
            detail="Annual reports hold the real statements"
          />
        </StatRow>
      </div>

      <Tabs tabs={tabs} active={view} onChange={setView} className="mb-5" />

      <TabPanel id="fundamentals" active={view === 'fundamentals'}>
        <FundamentalsPanel symbol={company.symbol} />
      </TabPanel>

      <TabPanel id="technicals" active={view === 'technicals'}>
        <TechnicalsPanel symbol={company.symbol} />
      </TabPanel>

      <TabPanel id="statements" active={view === 'statements'}>
        <StatementsTable financials={company.financials ?? []} />
      </TabPanel>
    </>
  );
}

/**
 * Starts a trade plan for this company.
 *
 * A 409 means a plan is already open, which is not an error the user needs to
 * recover from - the message names it and they can find it on the plans screen.
 */
function StartPlanButton({ company }: { company: CompanyDetail }) {
  const createPlan = useCreatePlan();

  return (
    <div className="text-right">
      <Button
        variant="primary"
        pending={createPlan.isPending}
        pendingLabel="Starting…"
        onClick={() => createPlan.mutate({ symbol: company.symbol })}
      >
        Start a trade plan
      </Button>
      {createPlan.isError ? (
        <p className="text-verdict-weak mt-1.5 max-w-xs text-xs">
          {isApiError(createPlan.error) && createPlan.error.isConflict ? (
            <>
              {createPlan.error.message}{' '}
              <Link to="/plans" className="underline">
                Open it
              </Link>
            </>
          ) : (
            'Could not start a plan.'
          )}
        </p>
      ) : null}
      {createPlan.isSuccess ? (
        <p className="mt-1.5 text-xs">
          <Link to={`/plans/${createPlan.data.id}`} className="text-accent underline">
            Plan started — work through the checklist
          </Link>
        </p>
      ) : null}
    </div>
  );
}

/**
 * The reported figures, exactly as stored.
 *
 * Deliberately free of derived ratios: this is the raw record, so a user can
 * reconcile it against the annual report. Judgements about these numbers live in
 * the fundamentals tab.
 */
function StatementsTable({ financials }: { financials: AnnualFinancials[] }) {
  if (financials.length === 0) {
    return <Notice>No financial statements are loaded for this company.</Notice>;
  }

  const rows: { label: string; pick: (year: AnnualFinancials) => string; group?: string }[] = [
    {
      group: 'Income statement',
      label: 'Revenue',
      pick: (y) => formatMoney(y.revenue, { abbreviate: true }),
    },
    { label: 'Net profit', pick: (y) => formatMoney(y.net_profit, { abbreviate: true }) },
    { label: 'EPS', pick: (y) => formatMoney(y.eps, { decimals: 2 }) },
    {
      group: 'Balance sheet',
      label: 'Total assets',
      pick: (y) => formatMoney(y.total_assets, { abbreviate: true }),
    },
    {
      label: 'Shareholders’ equity',
      pick: (y) => formatMoney(y.total_equity, { abbreviate: true }),
    },
    { label: 'Borrowings', pick: (y) => formatMoney(y.total_debt, { abbreviate: true }) },
    {
      group: 'Cash flow',
      label: 'Operating cash flow',
      pick: (y) => formatMoney(y.operating_cash_flow, { abbreviate: true }),
    },
    {
      label: 'Capital expenditure',
      pick: (y) => formatMoney(y.capital_expenditure, { abbreviate: true }),
    },
    {
      group: 'Shareholder returns',
      label: 'Dividend per share',
      pick: (y) => formatMoney(y.dividend_per_share, { decimals: 2 }),
    },
  ];

  return (
    <Card>
      <CardHeader
        title="Reported figures"
        description="As filed, in PKR. No ratios are derived here - see the fundamentals tab for those, and the annual report to verify any figure."
        actions={<Badge>{financials[0]?.source ?? ''}</Badge>}
      />
      <CardBodyFlush>
        <Table>
          <THead>
            <TR>
              <TH>Line item</TH>
              {financials.map((year) => (
                <TH key={year.fiscal_year} numeric>
                  FY{year.fiscal_year}
                </TH>
              ))}
            </TR>
          </THead>
          <TBody>
            {rows.map((row) => (
              <TR key={row.label}>
                <THRow>
                  {row.group ? (
                    <span className="text-ink-subtle mr-2 text-xs uppercase">{row.group}</span>
                  ) : null}
                  {row.label}
                </THRow>
                {financials.map((year) => (
                  <TD key={year.fiscal_year} numeric>
                    {row.pick(year)}
                  </TD>
                ))}
              </TR>
            ))}
          </TBody>
        </Table>
      </CardBodyFlush>
    </Card>
  );
}
