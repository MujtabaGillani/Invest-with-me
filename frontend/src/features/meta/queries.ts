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
