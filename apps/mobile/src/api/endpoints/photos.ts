/**
 * Photos endpoint functions (S16-001).
 */

import {apiClient} from '../ApiClient';

export interface PhotoAsset {
  id: string;
  file_id: string;
  taken_at: string | null;
  latitude: number | null;
  longitude: number | null;
  width: number | null;
  height: number | null;
  phash: string | null;
}

export interface PhotoListResponse {
  items: PhotoAsset[];
  next_cursor: string | null;
}

export async function listPhotos(
  cursor?: string,
  limit: number = 50,
): Promise<PhotoListResponse> {
  const qs = new URLSearchParams();
  qs.set('limit', String(limit));
  if (cursor) qs.set('cursor', cursor);

  return apiClient.request<PhotoListResponse>({
    path: `/photos?${qs.toString()}`,
  });
}

export async function getPhotoThumbnail(photoId: string): Promise<string> {
  return apiClient.request<string>({
    path: `/photos/${photoId}/thumbnail`,
  });
}
