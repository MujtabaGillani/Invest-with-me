import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, type RenderOptions, type RenderResult } from '@testing-library/react';
import type { ReactElement, ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Test render helper.
 *
 * Wraps the subject in the providers every component assumes exist - a query client
 * and a router. Each call gets a **fresh** query client, so cached data cannot leak
 * from one test into the next.
 *
 * Retries are off and logging is silenced: a test that renders an error state
 * should assert on it immediately rather than waiting out two retries, and React
 * Query's console noise about expected failures would drown the real output.
 */

function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
}

interface Options extends Omit<RenderOptions, 'wrapper'> {
  /** Initial history entries, for components that read route params. */
  routes?: string[];
}

export function renderWithProviders(ui: ReactElement, options: Options = {}): RenderResult {
  const { routes = ['/'], ...renderOptions } = options;
  const queryClient = createTestQueryClient();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={routes}>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...renderOptions });
}
