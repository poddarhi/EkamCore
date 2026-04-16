/**
 * usePhotoFaces — SWR hook for the lightbox face overlay (S13-008).
 *
 * Pass ``null`` or ``undefined`` to tear the SWR subscription down —
 * used by PhotoLightbox to stop fetching while the lightbox is
 * closed.
 */

import useSWR, { type SWRConfiguration } from "swr";

import { swrFetcher } from "../api/client";
import type { PhotoFacesResponse } from "../types/photos";

export function usePhotoFaces(
  photoId: string | null | undefined,
  config?: SWRConfiguration,
) {
  const key = photoId ? `/api/v1/photos/${photoId}/faces` : null;
  return useSWR<PhotoFacesResponse>(key, swrFetcher, config);
}
