import clsx from 'clsx';
import { NavLink, Outlet } from 'react-router-dom';

import { useOpenAlertCount } from '@/features/alerts/queries';
import { useMetadata } from '@/features/meta/queries';
import { useProfile } from '@/features/profile/queries';

import { SyntheticDataBanner } from './SyntheticDataBanner';

/**
 * The application frame: navigation, the data-provenance banner, and the footer
 * disclaimer.
 *
 * Navigation order follows the guide's own sequence rather than importance -
 * profile first, because deciding your own goals comes before looking at any
 * company; portfolio and alerts last, because they only exist once you have acted.
 * A user working through the app top to bottom is following the process.
 */

interface NavItem {
  to: string;
  label: string;
  /** One line explaining what the screen is for. */
  hint: string;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', hint: 'Where things stand' },
  { to: '/profile', label: 'Your plan', hint: 'Goals, horizon and risk limits' },
  { to: '/companies', label: 'Companies', hint: 'Browse and analyse' },
  { to: '/watchlist', label: 'Watchlist', hint: 'Researching, not yet owned' },
  { to: '/plans', label: 'Trade plans', hint: 'Checklists and exit rules' },
  { to: '/portfolio', label: 'Portfolio', hint: 'Holdings and trades' },
];

export function AppShell() {
  const openAlerts = useOpenAlertCount();
  const { data: profile } = useProfile();
  const { data: metadata } = useMetadata();

  // A user with no profile has not done the guide's first step. Flagged in the
  // navigation rather than behind a modal, so it prompts without blocking.
  const profileMissing = profile === null;

  return (
    <div className="flex min-h-full flex-col">
      <SyntheticDataBanner />

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 flex-col gap-6 px-4 py-6 sm:px-6 lg:flex-row">
        <aside className="lg:w-56 lg:shrink-0">
          <div className="mb-5">
            <NavLink to="/" className="text-ink text-lg font-semibold tracking-tight">
              PSX Invest
            </NavLink>
            <p className="text-ink-subtle mt-0.5 text-xs">Your process, written down</p>
          </div>

          <nav aria-label="Main">
            <ul className="space-y-0.5">
              {NAV_ITEMS.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    end={item.to === '/'}
                    title={item.hint}
                    className={({ isActive }) =>
                      clsx(
                        'flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                        isActive
                          ? 'bg-accent-subtle text-accent font-medium'
                          : 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
                      )
                    }
                  >
                    <span>{item.label}</span>
                    {item.to === '/profile' && profileMissing ? (
                      <span
                        title="You have not written down your goals and limits yet."
                        className="bg-verdict-weak-bg text-verdict-weak rounded-full px-1.5 py-0.5 text-[10px] font-medium"
                      >
                        Start here
                      </span>
                    ) : null}
                  </NavLink>
                </li>
              ))}

              <li>
                <NavLink
                  to="/alerts"
                  title="Your own rules, when they cross their thresholds"
                  className={({ isActive }) =>
                    clsx(
                      'flex items-center justify-between gap-2 rounded-md px-3 py-2 text-sm transition-colors',
                      isActive
                        ? 'bg-accent-subtle text-accent font-medium'
                        : 'text-ink-muted hover:bg-surface-sunken hover:text-ink',
                    )
                  }
                >
                  <span>Alerts</span>
                  {openAlerts > 0 ? (
                    <span className="bg-severity-warning numeric rounded-full px-1.5 py-0.5 text-[10px] font-semibold text-white">
                      {openAlerts}
                    </span>
                  ) : null}
                </NavLink>
              </li>
            </ul>
          </nav>
        </aside>

        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>

      <footer className="border-border text-ink-subtle mt-4 border-t px-4 py-5 text-xs sm:px-6">
        <div className="mx-auto max-w-[1400px] space-y-1">
          {/* The disclaimer comes from the API, so it is identical wherever the
              data is consumed - this UI, a script, or a future export. */}
          <p>{metadata?.disclaimer.text}</p>
          <p>
            This tool scores companies against a published checklist and records the rules you set
            for yourself. It does not rate stocks, predict prices, or tell you what to buy or sell.
          </p>
        </div>
      </footer>
    </div>
  );
}
