import { useState } from 'react';

import {
  Button,
  Card,
  CardBody,
  CardHeader,
  ErrorState,
  Notice,
  NumberField,
  TextAreaField,
  TriStateAnswer,
} from '@/components/ui';
import type { ChecklistKey, TradePlanDetail, TradePlanPatch } from '@/types';

import { useUpdatePlan } from './queries';

/**
 * Editing a draft plan: the five pre-buy questions, the thesis, and the exit rules.
 *
 * Two interaction decisions matter here.
 *
 * **Checklist answers save immediately.** Each answer is a small, independent
 * commitment, and the server recomputes `readiness` on every write - so answering a
 * question updates the blocking reasons in the same round trip. Batching them behind
 * a save button would hide that feedback until the end.
 *
 * **The written fields save on demand.** A thesis is drafted, not toggled; saving on
 * every keystroke would fight the user and flood the server.
 */

interface PlanEditorProps {
  plan: TradePlanDetail;
}

export function PlanEditor({ plan }: PlanEditorProps) {
  const editable = plan.status === 'draft';

  return (
    <div className="space-y-5">
      {!editable ? (
        <Notice title="This plan is locked">
          A plan is a record of a decision that has already been made, so it cannot be edited once
          committed to. That is the point: it is what you can compare against later, when the price
          is moving and the reasoning is harder to reconstruct.
        </Notice>
      ) : null}

      <ChecklistCard plan={plan} editable={editable} />
      {/* Keyed on the plan so navigating to another one starts with its values
          rather than the previous plan's half-edited text. */}
      <WrittenFieldsCard key={plan.id} plan={plan} editable={editable} />
    </div>
  );
}

/** The five pre-buy questions from guide section 5. */
function ChecklistCard({ plan, editable }: { plan: TradePlanDetail; editable: boolean }) {
  const updatePlan = useUpdatePlan();

  function answer(key: ChecklistKey, value: boolean) {
    updatePlan.mutate({ id: plan.id, patch: { [key]: value } });
  }

  return (
    <Card>
      <CardHeader
        title="Before you buy"
        description="Five questions. All five have to be a confident yes before this plan can be committed to - answering honestly is worth more than answering favourably."
      />
      <CardBody>
        <div className="divide-border divide-y">
          {plan.checklist.map((item) => (
            <TriStateAnswer
              key={item.key}
              question={item.question}
              value={item.answer}
              disabled={!editable || updatePlan.isPending}
              onChange={(value) => answer(item.key as ChecklistKey, value)}
            />
          ))}
        </div>

        {updatePlan.isError ? (
          <ErrorState error={updatePlan.error} title="Could not save that answer" />
        ) : null}
      </CardBody>
    </Card>
  );
}

/** The thesis, what would disprove it, and the exit rules. */
function WrittenFieldsCard({ plan, editable }: { plan: TradePlanDetail; editable: boolean }) {
  const updatePlan = useUpdatePlan();

  const [thesis, setThesis] = useState(plan.thesis ?? '');
  const [invalidation, setInvalidation] = useState(plan.invalidation_note ?? '');
  const [amount, setAmount] = useState(plan.intended_amount ?? '');
  const [target, setTarget] = useState(plan.profit_target_pct ?? '');
  const [stop, setStop] = useState(plan.stop_loss_pct ?? '');

  /**
   * Re-seed the inputs from the server's copy after a save.
   *
   * Done here rather than in an effect: syncing props into state from an effect
   * causes a cascading render, and React's guidance is to do it in the event that
   * caused the change. It matters practically too - the server normalises "25" to
   * "25.00", so without this the form would still look unsaved afterwards.
   *
   * Switching between plans is handled by the `key` the parent passes, which
   * remounts this component with fresh state.
   */
  function reseed(saved: TradePlanDetail) {
    setThesis(saved.thesis ?? '');
    setInvalidation(saved.invalidation_note ?? '');
    setAmount(saved.intended_amount ?? '');
    setTarget(saved.profit_target_pct ?? '');
    setStop(saved.stop_loss_pct ?? '');
  }

  const dirty =
    thesis !== (plan.thesis ?? '') ||
    invalidation !== (plan.invalidation_note ?? '') ||
    amount !== (plan.intended_amount ?? '') ||
    target !== (plan.profit_target_pct ?? '') ||
    stop !== (plan.stop_loss_pct ?? '');

  function save() {
    // Only send what changed. The API treats an omitted field as "leave alone",
    // so a narrow patch cannot clear something by accident.
    const patch: TradePlanPatch = {};
    if (thesis !== (plan.thesis ?? '')) patch.thesis = thesis.trim() || null;
    if (invalidation !== (plan.invalidation_note ?? ''))
      patch.invalidation_note = invalidation.trim() || null;
    if (amount !== (plan.intended_amount ?? '')) patch.intended_amount = amount || null;
    if (target !== (plan.profit_target_pct ?? '')) patch.profit_target_pct = target || null;
    if (stop !== (plan.stop_loss_pct ?? '')) patch.stop_loss_pct = stop || null;

    updatePlan.mutate({ id: plan.id, patch }, { onSuccess: reseed });
  }

  return (
    <Card>
      <CardHeader
        title="Why, how much, and when you would get out"
        description="Decide the exit now, while nothing is at stake. The guide's point is that this is much harder to do while watching the price move."
      />
      <CardBody className="space-y-4">
        <TextAreaField
          label="Why are you buying this?"
          value={thesis}
          disabled={!editable}
          onChange={(event) => setThesis(event.target.value)}
          hint="In your own words. If you cannot state the reason, you will not be able to tell later whether it has stopped being true."
          placeholder="For example: market-leading margins and low gearing; buying for domestic construction exposure over five years."
        />

        <TextAreaField
          label="What would prove you wrong?"
          value={invalidation}
          disabled={!editable}
          rows={3}
          onChange={(event) => setInvalidation(event.target.value)}
          hint="Writing this now, while it is hypothetical, is far easier than deciding during a loss."
          placeholder="For example: net margin below 10% for two consecutive years, or gearing above 0.6x to fund an unrelated acquisition."
        />

        <NumberField
          label="How much do you intend to invest?"
          suffix="PKR"
          value={amount}
          disabled={!editable}
          onChange={(event) => setAmount(event.target.value)}
          hint="Checked against the single-holding limit in your investor profile."
        />

        <div className="grid gap-4 sm:grid-cols-2">
          <NumberField
            label="Profit target"
            suffix="%"
            value={target}
            disabled={!editable}
            onChange={(event) => setTarget(event.target.value)}
            hint="The gain at which you would take something off the table. Having a number stops greed from keeping you in too long."
          />
          <NumberField
            label="Stop-loss"
            suffix="%"
            value={stop}
            disabled={!editable}
            onChange={(event) => setStop(event.target.value)}
            hint="The fall below your purchase price at which you would exit. This is what stops a small loss becoming a large one."
          />
        </div>

        {updatePlan.isError ? <ErrorState error={updatePlan.error} title="Could not save" /> : null}

        {editable ? (
          <div className="flex items-center gap-3">
            <Button
              variant="primary"
              disabled={!dirty}
              pending={updatePlan.isPending}
              pendingLabel="Saving…"
              onClick={save}
            >
              Save
            </Button>
            {dirty ? (
              <span className="text-ink-subtle text-xs">Unsaved changes</span>
            ) : updatePlan.isSuccess ? (
              <span className="text-verdict-strong text-xs">Saved.</span>
            ) : null}
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}
