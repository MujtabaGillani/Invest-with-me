import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router-dom';

import { AppProviders } from '@/app/AppProviders';
import { router } from '@/router';
import '@/styles/index.css';

/**
 * Entry point.
 *
 * `StrictMode` is on: it double-invokes effects in development, which surfaces
 * missing cleanup and accidental side effects during render - both worth catching
 * in a tool that records financial decisions.
 */

const container = document.getElementById('root');
if (!container) {
  // A missing root element means index.html and this file have diverged. Failing
  // loudly beats a blank page with nothing in the console.
  throw new Error('Root element #root was not found in the document.');
}

createRoot(container).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
