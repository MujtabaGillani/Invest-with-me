import { Link } from 'react-router-dom';

import { Card, CardBody, EmptyState } from '@/components/ui';

export function NotFoundPage() {
  return (
    <Card>
      <CardBody>
        <EmptyState
          title="That page does not exist"
          description="The link may be out of date, or the company symbol may have changed."
          action={
            <Link to="/" className="text-accent text-sm font-medium hover:underline">
              Back to the dashboard
            </Link>
          }
        />
      </CardBody>
    </Card>
  );
}
