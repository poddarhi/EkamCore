/**
 * Photo lightbox types (S13-008).
 */

export interface PhotoFaceBbox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface PhotoFaceItem {
  face_detection_id: string;
  bbox: PhotoFaceBbox;
  detection_score: number;
  cluster_id: string | null;
  trusted_person_id: string | null;
  trusted_person_display_name: string | null;
  trusted_person_avatar_url: string | null;
}

export interface PhotoFacesResponse {
  items: PhotoFaceItem[];
}
