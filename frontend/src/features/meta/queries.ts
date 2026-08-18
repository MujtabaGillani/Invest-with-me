import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/apiClient';
import { queryKeys } from '@/lib/queryKeys';
import type { EnumOption, Metadata } from '@/types';

import type { SelectOption } from '@/components/ui';

/**
 * Server metadata: vocabulary, labels and data provenance.
 *
 * Every dropdown in the app is built from this response rather than from a
 * hard-coded list. Sector labels, horizon descriptions and the wording of the five
 * pre-buy questions all live on the server, so there is exactly one copy and it
 * cannot drift from what the API accepts.
 */

function fetchMetadata(): Promise<Metadata> {
  return api.get<Metadata>('/meta');
}

export function useMetadata() {
  return useQuery({
    queryKey: queryKeys.meta,
    queryFn: fetchMetadata,
    // The vocabulary changes only on deploy, so it never needs refetching within
    // a session. `Infinity` also means every component can call this hook freely
    // without generating requests.
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/** Adapt the API's `EnumOption` list to the select control's shape. */
export function toSelectOptions(options: EnumOption[] | undefined): SelectOption[] {
  return (options ?? []).map((option) => ({
    value: option.value,
    label: option.label,
    description: option.description ?? null,
  }));
}

/**
 * Look up a sector's display label.
 *
 * Falls back to the raw value rather than rendering blank: if the server adds a
 * sector the client has not fetched yet, showing `new_sector` is worse than a
 * label but far better than an empty cell.
 */
export function useSectorLabel(): (sector: string) => string {
  const { data } = useMetadata();
  return (sector: string) =>
    data?.sectors.find((option) => option.value === sector)?.label ?? sector;
}

/**
 * Whether the market data behind every figure in the app is generated.
 *
 * Defaults to `true` while loading and on failure. That default is deliberate: if
 * the app cannot confirm the data is real, it must assume it is not and keep the
 * warning banner up. The opposite default would present invented figures as real
 * during exactly the moments when something is already wrong.
 */
export function useIsSyntheticData(): boolean {
  const { data } = useMetadata();
  return data?.provider.is_synthetic ?? true;
}
