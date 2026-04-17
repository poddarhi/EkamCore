/**
 * People endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';

export interface Person {
  id: string;
  display_name: string;
  canonical_contact_id: string | null;
  trust_source: string;
  confirmed_at: string | null;
}

export interface PersonListResponse {
  items: Person[];
  next_cursor: string | null;
}

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
