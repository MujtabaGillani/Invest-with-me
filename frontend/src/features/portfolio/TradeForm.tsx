import { useState } from 'react';

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Notice,
  NumberField,
  SelectField,
  TextAreaField,
  TextField,
} from '@/components/ui';
import { isApiError } from '@/lib/apiClient';
import { formatMoney, toNumber } from '@/lib/format';
import type { TradeInput } from '@/types';

import { useRecordTrade } from './queries';

/**
 * Record an executed trade.
 *
 * This form records something that has **already happened** at the broker - it does
 * not place an order, and the wording is careful about that throughout. Getting that
 * distinction wrong in the copy would be the single most dangerous ambiguity in the
 * application.
 *
 * The estimated total is shown live, because a mistyped quantity is the easiest
 * possible error to make here and the cheapest to catch before submitting.
 */
export function TradeForm({ defaultSymbol }: { defaultSymbol?: string }) {
  const [symbol, setSymbol] = useState(defaultSymbol ?? '');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [quantity, setQuantity] = useState('');
  const [price, setPrice] = useState('');
  const [fees, setFees] = useState('');
  const [executedAt, setExecutedAt] = useState('');
  const [note, setNote] = useState('');

  const recordTrade = useRecordTrade();

  const estimate = (() => {
    const q = toNumber(quantity);
    const p = toNumber(price);
    const f = toNumber(fees) ?? 0;
    if (q === null || p === null) return null;
    // A buy costs gross plus fees; a sell returns gross less fees.
    return side === 'buy' ? q * p + f : q * p - f;
  })();

  function submit(event: React.FormEvent) {
    event.preventDefault();

    const payload: TradeInput = {
      symbol: symbol.trim().toUpperCase(),
      side,
      quantity,
      price,
      fees: fees || '0',
      // A date-only input is sent as midnight UTC. Precision beyond the day is not
      // something a user reading a broker statement has, so asking for it would be
      // false precision.
      executed_at: executedAt ? new Date(`${executedAt}T00:00:00Z`).toISOString() : null,
      note: note.trim() || null,
    };

    recordTrade.mutate(payload, {
      onSuccess: () => {
        setQuantity('');
        setPrice('');
        setFees('');
        setNote('');
      },
    });
  }

  return (
    <Card>
      <CardHeader
        title="Record a trade"
        description="For a purchase or sale that has already gone through at your broker. This app does not place orders."
      />
      <CardBody>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Symbol"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="LUCK"
              required
              hint="PSX ticker. Case does not matter."
            />
            <SelectField
              label="Side"
              options={[
                { value: 'buy', label: 'Bought' },
                { value: 'sell', label: 'Sold' },
              ]}
              value={side}
              onChange={(event) => setSide(event.target.value as 'buy' | 'sell')}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <NumberField
              label="Shares"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              required
            />
            <NumberField
              label="Price per share"
              suffix="PKR"
              value={price}
              onChange={(event) => setPrice(event.target.value)}
              required
            />
            <NumberField
              label="Fees"
              suffix="PKR"
              value={fees}
              onChange={(event) => setFees(event.target.value)}
              hint="Brokerage, CDC and taxes."
            />
          </div>

          {estimate !== null ? (
            <p className="text-ink-muted numeric text-sm">
              {side === 'buy' ? 'Total cost' : 'Net proceeds'}:{' '}
              <span className="text-ink font-medium">{formatMoney(estimate)}</span>
            </p>
          ) : null}

          <TextField
            label="Date"
            type="date"
            value={executedAt}
            onChange={(event) => setExecutedAt(event.target.value)}
            hint="Leave blank for today. A past date is fine - back-filled trades replay in execution order, so they land in the right place in your cost basis."
          />

          <TextAreaField
            label="Note"
            rows={2}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            hint="Optional. Useful for imported history, or for why you deviated from a plan."
          />

          {recordTrade.isError ? (
            isApiError(recordTrade.error) && recordTrade.error.isBusinessRuleViolation ? (
              <Notice tone="caution" title="That trade does not fit your ledger">
                {recordTrade.error.message}
              </Notice>
            ) : (
              <ErrorState error={recordTrade.error} title="Could not record the trade" />
            )
          ) : null}

          <div className="flex items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              pending={recordTrade.isPending}
              pendingLabel="Recording…"
              disabled={!symbol || !quantity || !price}
            >
              Record {side === 'buy' ? 'purchase' : 'sale'}
            </Button>
            {recordTrade.isSuccess && !recordTrade.isPending ? (
              <span className="text-verdict-strong text-sm">
                Recorded{recordTrade.data.plan_id ? ' and linked to your plan.' : '.'}
              </span>
            ) : null}
          </div>
        </form>
      </CardBody>
    </Card>
  );
}
