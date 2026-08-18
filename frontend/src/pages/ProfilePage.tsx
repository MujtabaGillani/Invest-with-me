import { PageHeader } from '@/components/layout/PageHeader';
import { Card, CardBody, CardHeader, ErrorState, LoadingState, Notice } from '@/components/ui';
import { ProfileForm } from '@/features/profile/ProfileForm';
import { useProfile } from '@/features/profile/queries';

/**
 * The investor profile screen - the guide's first step.
 *
 * The warnings panel sits *beside* the form rather than after it, so a user editing
 * a limit sees the consequence immediately after saving. The warnings are computed
 * server-side and are the same list wherever the profile is shown.
 */
export function ProfilePage() {
  const { data: profile, isPending, isError, error, refetch } = useProfile();

  // Derived server-side and defaulted in the schema, so absent means "none".
  const warnings = profile?.warnings ?? [];

  return (
    <>
      <PageHeader
        title="Your plan"
        description="Decide these before looking at any company. Every position-size check, concentration warning and review reminder in this app is measured against what you write here."
      />

      {isPending ? (
        <Card>
          <LoadingState />
        </Card>
      ) : isError ? (
        <Card>
          <ErrorState error={error} onRetry={() => void refetch()} />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
          <Card>
            <CardHeader
              title={profile ? 'Your goals and limits' : 'Write down your goals and limits'}
              description={
                profile
                  ? 'Changing a limit re-checks every plan and holding against the new figure.'
                  : 'Nothing here is locked in - but writing it down before you buy is what makes the checks that follow meaningful.'
              }
            />
            <CardBody>
              <ProfileForm profile={profile ?? null} />
            </CardBody>
          </Card>

          <div className="space-y-4">
            {warnings.length > 0 ? (
              <Card>
                <CardHeader
                  title="Worth knowing"
                  description="Consequences of the answers you have given, not corrections."
                />
                <CardBody className="space-y-3">
                  {warnings.map((warning) => (
                    <p
                      key={warning}
                      className="text-ink-muted border-border border-l-2 pl-3 text-sm"
                    >
                      {warning}
                    </p>
                  ))}
                </CardBody>
              </Card>
            ) : profile ? (
              <Notice tone="positive" title="No concerns to flag">
                Your recorded answers are internally consistent, and the money-hygiene questions are
                both answered the way the guide recommends.
              </Notice>
            ) : null}

            <Notice title="Why this comes first">
              The guide is explicit that these answers matter more than any single stock pick. They
              also do real work here: a plan cannot be committed to without a position size checked
              against your own limit, and the portfolio warns you when a holding or a sector grows
              past the caps you set.
            </Notice>
          </div>
        </div>
      )}
    </>
  );
}
