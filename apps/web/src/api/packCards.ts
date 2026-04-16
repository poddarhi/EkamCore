/**
 * Pack cards API client (S14-009).
 */

import { apiFetch } from "./client";

const BASE = "/api/v1/pack-cards";

export interface PackCardItem {
  id: string;
  card_type: string;
  payload: Record<string, unknown>;
  target_date: string;
  acknowledged_at: string | null;
  acknowledged_action: string | null;
  snoozed_until: string | null;
}

export type AcknowledgeAction = "done" | "dismissed" | "snoozed";

export const packCardsApi = {
  list: (params: {
    target_date?: string;
    acknowledged?: boolean;
  } = {}): Promise<{ items: PackCardItem[] }> => {
    const qs = new URLSearchParams();
    if (params.target_date) qs.set("target_date", params.target_date);
    if (params.acknowledged !== undefined)
      qs.set("acknowledged", String(params.acknowledged));
    const q = qs.toString();
    return apiFetch<{ items: PackCardItem[] }>(
      `${BASE}${q ? `?${q}` : ""}`,
    );
  },

  acknowledge: (
    cardId: string,
    action: AcknowledgeAction,
    snoozedUntil?: string,
  ): Promise<unknown> =>
    apiFetch(`${BASE}/${cardId}/acknowledge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action,
        ...(snoozedUntil ? { snoozed_until: snoozedUntil } : {}),
      }),
    }),
};
