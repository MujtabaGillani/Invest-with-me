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
  NumberField,
  Table,
  TBody,
  TD,
  TextAreaField,
  TextField,
  TH,
  THead,
  THRow,
  TR,
} from '@/components/ui';
import {
  useAddToWatchlist,
  useRemoveFromWatchlist,
  useWatchlist,
} from '@/features/watchlist/queries';
import { isApiError } from '@/lib/apiClient';
import { formatDate, formatMoney, formatPercent } from '@/lib/format';

/**
 * The watchlist.
 *
 * A research note is required to add anything, with a real minimum length. That is
 * the guide's first listed mistake made structural: chasing hype is easy, and having
 * to articulate *why* before the app will track something is the cheapest guard
 * against it.
 */
export function WatchlistPage() {
  const [showForm, setShowForm] = useState(false);
  const { data: items, isPending, isError, error, refetch } = useWatchlist();
  const removeItem = useRemoveFromWatchlist();

  return (
    <>
      <PageHeader
        title="Watchlist"
        description="Companies you are researching but do not own. Note an entry price and the app will tell you when the market reaches it - which is a prompt to work through the checklist, not to buy."
        actions={
          <Button variant="primary" onClick={() => setShowForm((open) => !open)}>
            {showForm ? 'Cancel' : 'Watch a company'}
          </Button>
        }
      />

      {showForm ? (
        <div className="mb-5">
          <AddForm onAdded={() => setShowForm(false)} />
        </div>
      ) : null}

      <Card>
        {isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : isPending ? (
          <LoadingState />
        ) : items.length === 0 ? (
          <EmptyState
            title="Nothing on your watchlist"
            description="Add a company you want to keep an eye on, along with the reason. The reason is what you will read back when the price moves and you have to decide whether anything has actually changed."
            action={
              <Button variant="primary" onClick={() => setShowForm(true)}>
                Watch a company
              </Button>
            }
          />
        ) : (
          <CardBodyFlush>
            <Table>
              <THead>
                <TR>
                  <TH>Company</TH>
                  <TH numeric>Last close</TH>
                  <TH numeric>Your entry price</TH>
                  <TH>Why you are watching</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {items.map((item) => (
                  <TR key={item.id}>
                    <THRow className="align-top">
                      <Link
                        to={`/companies/${item.symbol}`}
                        className="text-accent font-semibold hover:underline"
                      >
                        {item.symbol}
                      </Link>
                      <p className="text-ink-subtle text-xs font-normal">{item.company_name}</p>
                      <p className="text-ink-subtle text-xs font-normal">{item.sector_label}</p>
                    </THRow>
                    <TD numeric className="align-top">
                      {formatMoney(item.last_close)}
                      <p className="text-ink-subtle text-xs">{formatDate(item.last_close_date)}</p>
                    </TD>
                    <TD numeric className="align-top">
                      {item.target_entry_price ? (
                        <>
                          {formatMoney(item.target_entry_price)}
                          <p
                            className={
                              item.entry_price_reached
                                ? 'text-verdict-strong text-xs'
                                : 'text-ink-subtle text-xs'
                            }
                          >
                            {item.entry_price_reached
                              ? 'Reached'
                              : `${formatPercent(item.distance_to_target_pct)} to go`}
                          </p>
                        </>
                      ) : (
                        <span className="text-ink-subtle text-xs">Not set</span>
                      )}
                    </TD>
                    <TD className="align-top">
                      <p className="text-ink-muted max-w-md text-sm">{item.research_note}</p>
                      {item.has_trade_plan ? (
                        <Link to="/plans" className="text-accent mt-1 inline-block text-xs">
                          <Badge className="bg-accent-subtle text-accent">Plan open</Badge>
                        </Link>
                      ) : null}
                    </TD>
                    <TD className="align-top">
                      <Button
                        size="sm"
                        variant="ghost"
                        pending={removeItem.isPending && removeItem.variables === item.id}
                        onClick={() => removeItem.mutate(item.id)}
                      >
                        Remove
                      </Button>
                    </TD>
                  </TR>
                ))}
              </TBody>
            </Table>
          </CardBodyFlush>
        )}
      </Card>

      <Notice tone="note" title="A price level is not a reason">
        Reaching your entry price says the market moved, not that the business improved. The
        checklist is what decides whether it is worth owning.
      </Notice>
    </>
  );
}

function AddForm({ onAdded }: { onAdded: () => void }) {
  const [symbol, setSymbol] = useState('');
  const [note, setNote] = useState('');
  const [targetPrice, setTargetPrice] = useState('');
  const addItem = useAddToWatchlist();

  // Mirrors the server's minimum so the button can explain itself rather than
  // producing a 422 the user has to decode.
  const noteTooShort = note.trim().length < 10;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    addItem.mutate(
      {
        symbol: symbol.trim().toUpperCase(),
        research_note: note.trim(),
        target_entry_price: targetPrice || null,
      },
      {
        onSuccess: () => {
          setSymbol('');
          setNote('');
          setTargetPrice('');
          onAdded();
        },
      },
    );
  }

  return (
    <Card>
      <CardHeader title="Watch a company" />
      <CardBody>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Symbol"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="FFC"
              required
            />
            <NumberField
              label="Entry price you would buy at"
              suffix="PKR"
              value={targetPrice}
              onChange={(event) => setTargetPrice(event.target.value)}
              hint="Optional. You will be told when the market reaches it."
            />
          </div>

          <TextAreaField
            label="Why are you watching this?"
            value={note}
            rows={3}
            onChange={(event) => setNote(event.target.value)}
            hint="Required. If the only reason is that it is moving or someone mentioned it, that is worth noticing now rather than after buying."
            placeholder="For example: stable urea margins and a long dividend record, but I want a better entry price before buying for income."
          />

          {addItem.isError ? (
            isApiError(addItem.error) && addItem.error.isConflict ? (
              <Notice tone="caution">{addItem.error.message}</Notice>
            ) : (
              <ErrorState error={addItem.error} title="Could not add that" />
            )
          ) : null}

          <Button
            type="submit"
            variant="primary"
            disabled={!symbol || noteTooShort}
            pending={addItem.isPending}
            pendingLabel="Adding…"
          >
            Add to watchlist
          </Button>
        </form>
      </CardBody>
    </Card>
  );
}
