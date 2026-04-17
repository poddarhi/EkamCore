/**
 * People endpoint functions (S16-001 + S16-006).
 */

import {apiClient} from '../ApiClient';

// ── Types ───────────────────────────────────────────────────────────────────

export interface Person {
  id: string;
  display_name: string;
  canonical_contact_id: string | null;
  trust_source: string;
  confirmed_at: string | null;
  face_count?: number;
  first_seen?: string;
  last_seen?: string;
}

export interface PersonListResponse {
  items: Person[];
  next_cursor: string | null;
}

export interface ReviewCluster {
  id: string;
  sample_face_ids: string[];
  face_count: number;
  top_candidate: {
    person_id: string;
    display_name: string;
    confidence: number;
  } | null;
  other_candidates: {
    person_id: string;
    display_name: string;
    confidence: number;
  }[];
}

export interface ReviewQueueResponse {
  items: ReviewCluster[];
  total: number;
}

// ── People CRUD ─────────────────────────────────────────────────────────────

export async function listPeople(
  cursor?: string,
  limit: number = 50,
  search?: string,
): Promise<PersonListResponse> {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (cursor) qs.set('cursor', cursor);
  if (search) qs.set('search', search);

  return apiClient.request<PersonListResponse>({
    path: `/people?${qs.toString()}`,
  });
}

export async function getPerson(personId: string): Promise<Person> {
  return apiClient.request<Person>({
    path: `/people/${personId}`,
  });
}

export async function getPersonAvatar(personId: string): Promise<string> {
  return apiClient.request<string>({
    path: `/people/${personId}/avatar`,
  });
}

export async function renamePerson(
  personId: string,
  displayName: string,
): Promise<Person> {
  return apiClient.request<Person>({
    path: `/people/${personId}`,
    method: 'PATCH',
    body: {display_name: displayName},
  });
}

export async function deletePerson(personId: string): Promise<void> {
  return apiClient.request<void>({
    path: `/people/${personId}`,
    method: 'DELETE',
  });
}

export async function mergePersons(
  keeperId: string,
  mergeIds: string[],
): Promise<Person> {
  return apiClient.request<Person>({
    path: `/people/${keeperId}/merge`,
    method: 'POST',
    body: {merge_ids: mergeIds},
  });
}

// ── Review Queue ────────────────────────────────────────────────────────────

export async function getReviewQueue(
  limit: number = 20,
): Promise<ReviewQueueResponse> {
  return apiClient.request<ReviewQueueResponse>({
    path: `/people/review-queue?limit=${limit}`,
  });
}

export async function confirmCluster(
  clusterId: string,
  personId: string,
): Promise<void> {
  return apiClient.request<void>({
    path: `/people/review-queue/${clusterId}/confirm`,
    method: 'POST',
    body: {person_id: personId},
  });
}

export async function rejectCluster(clusterId: string): Promise<void> {
  return apiClient.request<void>({
    path: `/people/review-queue/${clusterId}/reject`,
    method: 'POST',
  });
}

export async function skipCluster(clusterId: string): Promise<void> {
  return apiClient.request<void>({
    path: `/people/review-queue/${clusterId}/skip`,
    method: 'POST',
  });
}

// ── Person content ──────────────────────────────────────────────────────────

export async function getPersonPhotos(
  personId: string,
  cursor?: string,
): Promise<{items: {id: string; thumbnail_url: string; taken_at: string | null}[]; next_cursor: string | null}> {
  const qs = cursor ? `?cursor=${cursor}` : '';
  return apiClient.request({path: `/people/${personId}/photos${qs}`});
}

export async function getPersonFiles(
  personId: string,
  cursor?: string,
): Promise<{items: {id: string; filename: string; mime_type: string}[]; next_cursor: string | null}> {
  const qs = cursor ? `?cursor=${cursor}` : '';
  return apiClient.request({path: `/people/${personId}/files${qs}`});
}

export async function getPersonEvents(
  personId: string,
  cursor?: string,
): Promise<{items: {id: string; title: string; start_at: string}[]; next_cursor: string | null}> {
  const qs = cursor ? `?cursor=${cursor}` : '';
  return apiClient.request({path: `/people/${personId}/events${qs}`});
}
