/**
 * SWR hook for pack cards (S14-009).
 */

import useSWR, { type SWRConfiguration } from "swr";

import { swrFetcher } from "../api/client";
import type { PackCardItem } from "../api/packCards";

export function usePackCards(
  targetDate?: string,
  config?: SWRConfiguration,
) {
  const qs = targetDate
    ? `?target_date=${targetDate}&acknowledged=false`
    : "?acknowledged=false";
  return useSWR<{ items: PackCardItem[] }>(
    `/api/v1/pack-cards${qs}`,
    swrFetcher,
    config,
  );
}
