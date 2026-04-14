/**
 * People / TrustedPersons API client (S13-001).
 *
 * Every function goes through `apiFetch` so auth headers, CSRF, and
 * error parsing are handled centrally. Never log request bodies — they
 * may contain person display names. The fetch wrapper already excludes
 * bodies from its logs.
 */

import type {
  ConfirmCandidateRequest,
  CreatePersonRequest,
  MergeRequest,
  PaginatedOperations,
  PaginatedPersons,
  PersonOperationResult,
  RejectClusterRequest,
  SplitRequest,
  TrustedPerson,
} from "../types/people";
import { apiFetch } from "./client";

const BASE = "/api/v1/people";

function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== "",
  );
  if (entries.length === 0) return "";
  const qs = new URLSearchParams();
  for (const [k, v] of entries) {
    qs.set(k, String(v));
  }
  return `?${qs.toString()}`;
}

export interface ListPeopleParams {
  limit?: number;
  cursor?: string;
  search?: string;
}

export const peopleApi = {
  list: (params: ListPeopleParams = {}): Promise<PaginatedPersons> =>
    apiFetch<PaginatedPersons>(`${BASE}${buildQuery(params)}`),

  get: (personId: string): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(`${BASE}/${personId}`),

  create: (body: CreatePersonRequest): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(BASE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  confirmCandidate: (body: ConfirmCandidateRequest): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(`${BASE}/confirm-candidate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  rejectCluster: (body: RejectClusterRequest): Promise<void> =>
    apiFetch<void>(`${BASE}/reject-cluster`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  rename: (personId: string, display_name: string): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(`${BASE}/${personId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ display_name }),
    }),

  delete: (personId: string): Promise<void> =>
    apiFetch<void>(`${BASE}/${personId}`, { method: "DELETE" }),

  merge: (body: MergeRequest): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(`${BASE}/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  split: (personId: string, body: SplitRequest): Promise<TrustedPerson> =>
    apiFetch<TrustedPerson>(`${BASE}/${personId}/split`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  undoLast: (): Promise<PersonOperationResult> =>
    apiFetch<PersonOperationResult>(`${BASE}/operations/undo-last`, {
      method: "POST",
    }),

  undoOperation: (operationId: string): Promise<PersonOperationResult> =>
    apiFetch<PersonOperationResult>(
      `${BASE}/operations/${operationId}/undo`,
      { method: "POST" },
    ),

  listOperations: (limit = 50): Promise<PaginatedOperations> =>
    apiFetch<PaginatedOperations>(`${BASE}/operations${buildQuery({ limit })}`),
};

export type PeopleApi = typeof peopleApi;
