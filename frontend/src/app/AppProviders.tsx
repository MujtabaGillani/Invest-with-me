import { QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { createQueryClient } from '@/lib/queryClient';

/**
 * Application-wide providers.
 *
 * The query client is created inside `useState` rather than at module scope. At
 * module scope it would be shared between test renders, so cached data from one
 * test would leak into the next - and in a future server-rendered setup, between
 * requests.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
