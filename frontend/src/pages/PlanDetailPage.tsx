import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { PageHeader } from '@/components/layout/PageHeader';
import {
  Button,
  Card,
  CardBody,
  ErrorState,
  LoadingState,
  PlanStatusBadge,
  TextAreaField,
} from '@/components/ui';
import { PlanEditor } from '@/features/plans/PlanEditor';
import { PlanReadiness } from '@/features/plans/PlanReadiness';
import { PlanReviewJournal } from '@/features/plans/PlanReviewJournal';
import { useAbandonPlan, useClosePlan, usePlan } from '@/features/plans/queries';
import { isApiError } from '@/lib/apiClient';
import { formatDateTime } from '@/lib/format';
import type { TradePlanDetail } from '@/types';

/**
 * One trade plan.
 *
 * Laid out with the editor on the left and readiness on the right, so answering a
 * checklist question and watching a blocking reason disappear happens in one glance.
 */
export function PlanDetailPage() {
  const { planId } = useParams<{ planId: string }>();
  const numericId = Number(planId);
  const {
    data: plan,
    isPending,
    isError,
    error,
    refetch,
  } = usePlan(Number.isFinite(numericId) && numericId > 0 ? numericId : undefined);

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
            <p className="text-ink text-sm font-medium">That plan does not exist</p>
            <p className="text-ink-muted mt-1 text-sm">
              <Link to="/plans" className="text-accent hover:underline">
                Back to your plans
              </Link>
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

  return (
    <>
      <PageHeader
        title={`Plan: ${plan.symbol}`}
        description={
          <>
            {plan.company_name} ·{' '}
            <Link to={`/companies/${plan.symbol}`} className="text-accent hover:underline">
              Run the checklist against the numbers
            </Link>
            {plan.committed_at ? ` · Committed ${formatDateTime(plan.committed_at)}` : null}
          </>
        }
        actions={
          <div className="flex items-center gap-3">
            <PlanStatusBadge status={plan.status} />
            <LifecycleActions plan={plan} />
          </div>
        }
      />

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <PlanEditor plan={plan} />
          <PlanReviewJournal plan={plan} />
        </div>
        <div>
          <PlanReadiness plan={plan} />
        </div>
      </div>
    </>
  );
}

/**
 * Abandon and close.
 *
 * Abandoning asks for a reason before doing anything. A decision not to buy is worth
 * recording - re-reading it is what stops the same idea coming back on the same
 * flimsy basis six months later.
 */
function LifecycleActions({ plan }: { plan: TradePlanDetail }) {
  const [showAbandon, setShowAbandon] = useState(false);
  const [reason, setReason] = useState('');
  const abandon = useAbandonPlan();
  const close = useClosePlan();

  const canAbandon = plan.status === 'draft' || plan.status === 'ready';
  const canClose = plan.status === 'executed';

  if (!canAbandon && !canClose) return null;

  return (
    <div className="text-right">
      <div className="flex gap-2">
        {canAbandon ? (
          <Button variant="danger" size="sm" onClick={() => setShowAbandon((open) => !open)}>
            Abandon
          </Button>
        ) : null}
        {canClose ? (
          <Button
            size="sm"
            pending={close.isPending}
            pendingLabel="Closing…"
            onClick={() => close.mutate(plan.id)}
          >
            Mark position closed
          </Button>
        ) : null}
      </div>

      {showAbandon ? (
        <div className="bg-surface-raised border-border mt-2 w-80 rounded-md border p-3 text-left shadow-sm">
          <TextAreaField
            label="Why are you not buying?"
            rows={3}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            hint="Kept in the plan's journal. Optional, but this is the note that saves you from revisiting the same idea unchanged."
          />
          <div className="mt-3 flex gap-2">
            <Button
              variant="danger"
              size="sm"
              pending={abandon.isPending}
              pendingLabel="Abandoning…"
              onClick={() =>
                abandon.mutate(
                  { id: plan.id, ...(reason.trim() ? { reason: reason.trim() } : {}) },
                  { onSuccess: () => setShowAbandon(false) },
                )
              }
            >
              Confirm
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setShowAbandon(false)}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
