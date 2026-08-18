import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Badge,
  Button,
  Card,
  CardBodyFlush,
  CardFooter,
  EmptyState,
  ErrorState,
  SelectField,
  Table,
  TableSkeleton,
  TBody,
  TD,
  TH,
  THead,
  THRow,
  TR,
  TextField,
} from '@/components/ui';
import { COMPANIES_PAGE_SIZE, useCompanies } from '@/features/companies/queries';
import { toSelectOptions, useMetadata } from '@/features/meta/queries';
import { formatDate, formatMoney } from '@/lib/format';

/**
 * Company browser.
 *
 * Search and sector filters live in the URL, so a filtered view can be linked or
 * bookmarked and the back button behaves. Paging state lives in component state,
 * because it is transient in a way a filter is not.
 *
 * Search is not debounced. The dataset is 24 companies and the query is served in
 * single-digit milliseconds; debouncing would add latency the user can feel in
 * exchange for saving requests that cost nothing. Worth adding the moment this
 * points at a real market feed.
 */
export function CompaniesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [offset, setOffset] = useState(0);

  const search = searchParams.get('search') ?? '';
  const sector = searchParams.get('sector') ?? '';

  const { data: metadata } = useMetadata();
  const { data, isPending, isError, error, refetch, isPlaceholderData } = useCompanies({
    search: search || undefined,
    sector: sector || undefined,
    offset,
  });

  function updateFilter(key: 'search' | 'sector', value: string) {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
    // Any filter change invalidates the current page number.
    setOffset(0);
  }

  const total = data?.total ?? 0;
  const shown = data?.items.length ?? 0;
  const hasMore = offset + shown < total;

  return (
    <>
      <PageHeader
        title="Companies"
        description="Pick a company to run the fundamentals checklist against it. The list shows the latest close held locally and whether there is enough data for each kind of analysis."
      />

      <Card>
        <div className="border-border grid gap-4 border-b px-5 py-4 sm:grid-cols-2">
          <TextField
            label="Search"
            value={search}
            onChange={(event) => updateFilter('search', event.target.value)}
            placeholder="Symbol or company name"
            hint="Matches either the ticker or the registered name."
          />
          <SelectField
            label="Sector"
            options={toSelectOptions(metadata?.sectors)}
            value={sector}
            placeholder="All sectors"
            onChange={(event) => updateFilter('sector', event.target.value)}
            hint="Valuation and gearing are only meaningful against companies in the same sector."
          />
        </div>

        {isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : isPending ? (
          <TableSkeleton columns={5} />
        ) : data.items.length === 0 ? (
          <EmptyState
            title="No companies match"
            description="Try a different search term, or clear the sector filter."
          />
        ) : (
          <>
            <CardBodyFlush className={isPlaceholderData ? 'opacity-60 transition-opacity' : ''}>
              <Table>
                <THead>
                  <TR>
                    <TH>Symbol</TH>
                    <TH>Company</TH>
                    <TH>Sector</TH>
                    <TH numeric>Last close</TH>
                    <TH>Data available</TH>
                  </TR>
                </THead>
                <TBody>
                  {data.items.map((company) => (
                    <TR key={company.id}>
                      <THRow>
                        <Link
                          to={`/companies/${company.symbol}`}
                          className="text-accent font-semibold hover:underline"
                        >
                          {company.symbol}
                        </Link>
                      </THRow>
                      <TD className="text-ink-muted">{company.name}</TD>
                      <TD className="text-ink-muted">{company.sector_label}</TD>
                      <TD numeric>
                        {formatMoney(company.last_close)}
                        <span className="text-ink-subtle ml-2 text-xs">
                          {formatDate(company.last_close_date)}
                        </span>
                      </TD>
                      <TD>
                        <div className="flex gap-1.5">
                          {/* Shown so a user knows which tabs will be useful before
                              clicking through, rather than meeting an error. */}
                          {company.has_financials ? (
                            <Badge className="bg-verdict-strong-bg text-verdict-strong">
                              Statements
                            </Badge>
                          ) : (
                            <Badge title="No filings loaded, so the fundamentals checklist cannot run.">
                              No statements
                            </Badge>
                          )}
                          {company.has_price_history ? (
                            <Badge className="bg-verdict-adequate-bg text-verdict-adequate">
                              Prices
                            </Badge>
                          ) : (
                            <Badge title="No price history loaded.">No prices</Badge>
                          )}
                        </div>
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
                  onClick={() => setOffset(Math.max(0, offset - COMPANIES_PAGE_SIZE))}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  disabled={!hasMore}
                  onClick={() => setOffset(offset + COMPANIES_PAGE_SIZE)}
                >
                  Next
                </Button>
              </div>
            </CardFooter>
          </>
        )}
      </Card>
    </>
  );
}
