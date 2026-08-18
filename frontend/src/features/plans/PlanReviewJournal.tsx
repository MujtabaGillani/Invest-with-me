import { useState } from 'react';

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CheckboxField,
  ErrorState,
  Notice,
  TextAreaField,
} from '@/components/ui';
import { formatDateTime, formatRelativeDays } from '@/lib/format';
import type { TradePlanDetail } from '@/types';

import { useRecordReview } from './queries';

/**
 * The thesis check-in journal - guide section 6.
 *
 * Append-only, newest first. The value is in the sequence: three consecutive entries
 * all saying "margins still slipping" is how a user notices they have been
 * rationalising a position rather than reassessing it. That is why entries cannot be
 * edited or deleted.
 *
 * The note is required with a real minimum length, because recording a review is what
 * clears the review-due alert. A one-word entry would silence the reminder without any
 * thinking having happened, which is worse than no reminder at all.
 */
export function PlanReviewJournal({ plan }: { plan: TradePlanDetail }) {
  const reviewable = plan.status === 'ready' || plan.status === 'executed';

  return (
    <Card>
      <CardHeader
        title="Thesis check-ins"
        description="Does the reason you bought this still hold? That question matters more than any price move."
        actions={
          plan.last_reviewed_at ? (
            <span className="text-ink-subtle text-xs">
              Last reviewed {formatRelativeDays(plan.last_reviewed_at)}
            </span>
          ) : null
        }
      />
      <CardBody className="space-y-4">
        {reviewable ? <ReviewForm plan={plan} /> : null}

        {plan.reviews && plan.reviews.length > 0 ? (
          <ol className="divide-border divide-y">
            {plan.reviews.map((review) => (
              <li key={review.id} className="py-3 first:pt-0 last:pb-0">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-ink-subtle text-xs">
                    {formatDateTime(review.created_at)}
                  </span>
                  {!review.thesis_still_valid ? (
                    <span className="text-verdict-weak text-xs font-medium">
                      Thesis recorded as no longer holding
                    </span>
                  ) : null}
                </div>
                <p className="text-ink mt-1 text-sm whitespace-pre-line">{review.note}</p>
              </li>
            ))}
          </ol>
        ) : reviewable ? (
          <Notice>
            No check-ins recorded yet. Committing to the plan counted as the first one.
          </Notice>
        ) : (
          <Notice>Check-ins are recorded against a plan you have committed to or acted on.</Notice>
        )}
      </CardBody>
    </Card>
  );
}

function ReviewForm({ plan }: { plan: TradePlanDetail }) {
  const [note, setNote] = useState('');
  const [stillValid, setStillValid] = useState(true);
  const recordReview = useRecordReview();

  // The server enforces the same minimum; checking here as well lets the button
  // explain itself rather than producing a 422 the user has to interpret.
  const tooShort = note.trim().length < 10;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    recordReview.mutate(
      { id: plan.id, review: { note: note.trim(), thesis_still_valid: stillValid } },
      {
        onSuccess: () => {
          setNote('');
          setStillValid(true);
        },
      },
    );
  }

  return (
    <form onSubmit={submit} className="border-border space-y-3 border-b pb-4">
      <TextAreaField
        label="Record a check-in"
        value={note}
        rows={3}
        onChange={(event) => setNote(event.target.value)}
        hint="What did you re-check, and what did you conclude? Profits, debt, margins, management - whatever your thesis rested on."
        placeholder="For example: re-read the half-year accounts. Margin held at 17% and gearing is unchanged, so the reason I bought still holds."
      />

      <CheckboxField
        label="The reason I bought this still holds"
        hint="Unticking this records that your thesis has broken. It does not sell anything - the decision stays with you."
        checked={stillValid}
        onChange={(event) => setStillValid(event.target.checked)}
      />

      {recordReview.isError ? (
        <ErrorState error={recordReview.error} title="Could not record that" />
      ) : null}

      <div className="flex items-center gap-3">
        <Button
          type="submit"
          variant="primary"
          size="sm"
          disabled={tooShort}
          pending={recordReview.isPending}
          pendingLabel="Recording…"
        >
          Record check-in
        </Button>
        {tooShort && note.length > 0 ? (
          <span className="text-ink-subtle text-xs">
            A little more detail — this is what you will read back later.
          </span>
        ) : null}
      </div>
    </form>
  );
}
