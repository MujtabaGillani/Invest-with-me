import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { MetricVerdict } from '@/types';

import { AnswerBadge, PlanStatusBadge, VerdictBadge } from './Badge';

/**
 * Badge labelling.
 *
 * These tests exist to protect the vocabulary, which is the product constraint made
 * visible. Two things must never drift:
 *
 * 1. A weak metric reads as "Weak", never as an instruction to sell.
 * 2. "Not enough data" is distinguishable from a bad result - conflating them would
 *    make the tool actively misleading about companies with thin filings.
 */

describe('VerdictBadge', () => {
  it('labels each verdict with a judgement, never an action', () => {
    const labels: Record<MetricVerdict, string> = {
      strong: 'Strong',
      adequate: 'Adequate',
      weak: 'Weak',
      insufficient_data: 'Not enough data',
    };

    for (const [verdict, label] of Object.entries(labels)) {
      const { unmount } = render(<VerdictBadge verdict={verdict as MetricVerdict} />);
      expect(screen.getByText(label)).toBeInTheDocument();
      unmount();
    }
  });

  it('never uses buy or sell language', () => {
    const verdicts: MetricVerdict[] = ['strong', 'adequate', 'weak', 'insufficient_data'];

    for (const verdict of verdicts) {
      const { container, unmount } = render(<VerdictBadge verdict={verdict} />);
      const text = (container.textContent ?? '').toLowerCase();
      for (const forbidden of ['buy', 'sell', 'avoid', 'recommend']) {
        expect(text).not.toContain(forbidden);
      }
      unmount();
    }
  });

  it('explains that insufficient data is not a bad result', () => {
    render(<VerdictBadge verdict="insufficient_data" />);
    expect(screen.getByText('Not enough data')).toHaveAttribute(
      'title',
      expect.stringContaining('not the same as a bad result'),
    );
  });
});

describe('AnswerBadge', () => {
  it('distinguishes unanswered from answered no', () => {
    // The API models these separately, and collapsing them here would make an
    // unfinished checklist look like a failed one.
    const { unmount } = render(<AnswerBadge answer={null} />);
    expect(screen.getByText('Unanswered')).toBeInTheDocument();
    unmount();

    render(<AnswerBadge answer={false} />);
    expect(screen.getByText('No')).toBeInTheDocument();
    expect(screen.queryByText('Unanswered')).not.toBeInTheDocument();
  });

  it('treats undefined the same as unanswered', () => {
    render(<AnswerBadge answer={undefined} />);
    expect(screen.getByText('Unanswered')).toBeInTheDocument();
  });
});

describe('PlanStatusBadge', () => {
  it('describes ready as committed rather than as a signal to act', () => {
    render(<PlanStatusBadge status="ready" />);
    const badge = screen.getByText('Committed');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveAttribute('title', expect.stringContaining('not yet acted on'));
  });

  it('explains that an abandoned plan is kept deliberately', () => {
    render(<PlanStatusBadge status="abandoned" />);
    expect(screen.getByText('Abandoned')).toHaveAttribute(
      'title',
      expect.stringContaining('decision journal'),
    );
  });
});
