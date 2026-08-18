import { createBrowserRouter } from 'react-router-dom';

import { AppShell } from '@/components/layout/AppShell';
import { AlertsPage } from '@/pages/AlertsPage';
import { BuySellPage } from '@/pages/BuySellPage';
import { CompaniesPage } from '@/pages/CompaniesPage';
import { CompanyPage } from '@/pages/CompanyPage';
import { DashboardPage } from '@/pages/DashboardPage';
import { MoneyPage } from '@/pages/MoneyPage';
import { NotFoundPage } from '@/pages/NotFoundPage';
import { PlanDetailPage } from '@/pages/PlanDetailPage';
import { PlansPage } from '@/pages/PlansPage';
import { PortfolioPage } from '@/pages/PortfolioPage';
import { ProfilePage } from '@/pages/ProfilePage';
import { WatchlistPage } from '@/pages/WatchlistPage';

/**
 * Route table.
 *
 * Flat and eagerly imported. The whole application is eleven screens and the bundle
 * is small, so route-level code splitting would add loading states and a
 * `Suspense` boundary per route in exchange for no measurable gain. Worth
 * revisiting only if a heavy dependency (a charting library, a spreadsheet export)
 * lands on one page.
 *
 * `/companies/:symbol` takes the ticker rather than a numeric id, because the
 * symbol is what a user recognises and would paste into the address bar.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <BuySellPage /> },
      { path: 'profile', element: <ProfilePage /> },
      // The simplified screens. `/` is the buy/sell answer, since that is what the
      // app is opened for; the original overview moves to `/dashboard` and stays
      // reachable under "Advanced".
      { path: 'money', element: <MoneyPage /> },
      { path: 'dashboard', element: <DashboardPage /> },
      { path: 'companies', element: <CompaniesPage /> },
      { path: 'companies/:symbol', element: <CompanyPage /> },
      { path: 'watchlist', element: <WatchlistPage /> },
      { path: 'plans', element: <PlansPage /> },
      { path: 'plans/:planId', element: <PlanDetailPage /> },
      { path: 'portfolio', element: <PortfolioPage /> },
      { path: 'alerts', element: <AlertsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
