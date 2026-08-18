import { useState } from 'react';
import { Link } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Button,
  Card,
  CardBody,
  CheckboxField,
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  SeverityBadge,
} from '@/components/ui';
import {
  useAcknowledgeAlert,
  useAcknowledgeAllAlerts,
  useAlerts,
  useEvaluateAlerts,
} from '@/features/alerts/queries';
import { formatDateTime } from '@/lib/format';
import type { Alert, AlertKind } from '@/types';

/**
 * Alerts.
 *
 * Every alert here is one of the user's **own** pre-committed rules crossing its
 * threshold - a profit target they chose, a stop-loss they set, a concentration limit
 * they declared. None is a prediction, and the copy on this page works hard to keep
 * that clear, because an alert that reads as a recommendation would undo the whole
 * point of writing the rules down in advance.
 *
 * Re-checking is an explicit button rather than something that happens on load: the
 * user gets told what changed, and a page visit never quietly writes to the database.
 */

/** What each alert kind means, and what the user's next step actually is. */
const KIND_GUIDANCE: Record<AlertKind, string> = {
  profit_target_reached:
    'You set this target before buying. Selling some, all, or none of it is still your call - the alert only says the level you chose has been reached.',
  stop_loss_breached:
    'This is the rule you wrote down to stop a small loss becoming a large one. Worth acting on deliberately rather than waiting to see.',
  thesis_review_due:
    'Re-read why you bought this and check whether that reason still holds. Recording a check-in clears this.',
  position_concentration:
    'One holding has grown past the share of the portfolio you said you were comfortable with. Trimming it is risk management, not an admission of a mistake.',
  sector_concentration:
    'One sector is above your own limit. Companies in a sector tend to fall together.',
  watchlist_entry_price_reached:
    'The market reached the price you noted. That says the price moved, not that the business improved - the checklist decides the rest.',
  fundamental_red_flag:
    'Something in the reported figures changed in a way that may undermine your reason for owning this. A change like this matters more than a price move.',
};

export function AlertsPage() {
  const [includeAcknowledged, setIncludeAcknowledged] = useState(false);
  const { data: alerts, isPending, isError, error, refetch } = useAlerts(includeAcknowledged);
  const evaluate = useEvaluateAlerts();
  const acknowledgeAll = useAcknowledgeAllAlerts();

  const openCount = (alerts ?? []).filter((alert) => !alert.is_acknowledged).length;

  return (
    <>
      <PageHeader
        title="Alerts"
        description="Your own rules, when they cross their thresholds. Nothing here is a recommendation from this app."
        actions={
          <div className="flex gap-2">
            <Button
              variant="primary"
              pending={evaluate.isPending}
              pendingLabel="Checking…"
              onClick={() => evaluate.mutate()}
            >
              Re-check now
            </Button>
            {openCount > 0 ? (
              <Button
                pending={acknowledgeAll.isPending}
                pendingLabel="Dismissing…"
                onClick={() => acknowledgeAll.mutate()}
              >
                Dismiss all
              </Button>
            ) : null}
          </div>
        }
      />

      {evaluate.isSuccess && !evaluate.isPending ? (
        <Notice tone="note">
          {evaluate.data.created} new, {evaluate.data.already_open} still open,{' '}
          {evaluate.data.resolved} no longer applicable. {evaluate.data.note}
        </Notice>
      ) : null}

      {evaluate.isError ? (
        <ErrorState error={evaluate.error} title="Could not re-check your rules" />
      ) : null}

      <div className="mt-4 mb-4">
        <CheckboxField
          label="Include alerts I have already dismissed"
          checked={includeAcknowledged}
          onChange={(event) => setIncludeAcknowledged(event.target.checked)}
          hint="Dismissed alerts are kept as part of your decision journal, never deleted."
        />
      </div>

      <Card>
        {isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : isPending ? (
          <LoadingState />
        ) : alerts.length === 0 ? (
          <EmptyState
            title={includeAcknowledged ? 'No alerts recorded' : 'Nothing needs your attention'}
            description="Alerts appear when one of the rules you set for yourself is crossed - a profit target, a stop-loss, a concentration limit, or a review falling due. Use “Re-check now” to run them against the latest stored prices."
          />
        ) : (
          <CardBody className="divide-border divide-y">
            {alerts.map((alert) => (
              <AlertRow key={alert.id} alert={alert} />
            ))}
          </CardBody>
        )}
      </Card>
    </>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const acknowledge = useAcknowledgeAlert();

  return (
    <article className="py-4 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex items-center gap-2">
            <SeverityBadge severity={alert.severity} />
            {alert.symbol ? (
              <Link
                to={`/companies/${alert.symbol}`}
                className="text-accent text-sm font-semibold hover:underline"
              >
                {alert.symbol}
              </Link>
            ) : null}
            <span className="text-ink-subtle text-xs">{formatDateTime(alert.created_at)}</span>
            {alert.is_acknowledged ? (
              <span className="text-ink-subtle text-xs">
                · dismissed {formatDateTime(alert.acknowledged_at)}
              </span>
            ) : null}
          </div>

          {/* The server's own wording. Never re-phrased client-side, because the
              careful distinction between "your rule fired" and "you should act" is
              in that wording. */}
          <p className="text-ink text-sm">{alert.message}</p>
          <p className="text-ink-muted mt-1.5 max-w-2xl text-xs">{KIND_GUIDANCE[alert.kind]}</p>
        </div>

        {!alert.is_acknowledged ? (
          <Button
            size="sm"
            variant="ghost"
            pending={acknowledge.isPending}
            onClick={() => acknowledge.mutate(alert.id)}
          >
            Dismiss
          </Button>
        ) : null}
      </div>
    </article>
  );
}
