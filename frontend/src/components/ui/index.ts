/**
 * Barrel for the UI primitives.
 *
 * Kept to *primitives only* - nothing feature-specific is re-exported here, so
 * importing from `@/components/ui` can never pull in a feature module and create
 * an import cycle.
 */

export { AnswerBadge, Badge, PlanStatusBadge, SeverityBadge, VerdictBadge } from './Badge';
export { Button } from './Button';
export { Card, CardBody, CardBodyFlush, CardFooter, CardHeader } from './Card';
export { Table, TBody, TD, TH, THead, THRow, TR } from './DataTable';
export { EmptyState, ErrorState, LoadingState, Notice, Spinner, TableSkeleton } from './feedback';
export {
  CheckboxField,
  NumberField,
  SelectField,
  TextAreaField,
  TextField,
  TriStateAnswer,
  type SelectOption,
} from './fields';
export { PriceChart, Sparkline } from './Sparkline';
export { StatRow, StatTile } from './StatTile';
export { TabPanel, Tabs, type TabDefinition } from './Tabs';
