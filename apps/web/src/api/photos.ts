/**
 * Photos API client (S13-008).
 *
 * The full-resolution image itself is fetched directly by the
 * browser via `<img src="/api/v1/photos/:id/full">` — routing it
 * through ``apiFetch`` would copy the bytes through JS memory for
 * no gain. This module only exposes the JSON companion endpoints.
 */

import type { PhotoFacesResponse } from "../types/photos";
import { apiFetch } from "./client";

const BASE = "/api/v1/photos";

export const photosApi = {
  getFaces: (photoId: string): Promise<PhotoFacesResponse> =>
    apiFetch<PhotoFacesResponse>(`${BASE}/${photoId}/faces`),
};

export type PhotosApi = typeof photosApi;
