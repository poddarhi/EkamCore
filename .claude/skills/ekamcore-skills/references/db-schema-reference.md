# Database Schema Reference (from ART-09)

## Universal Columns (every content table)
- `id UUID DEFAULT gen_uuid_v7() PRIMARY KEY`
- `created_at TIMESTAMPTZ DEFAULT now() NOT NULL`
- `updated_at TIMESTAMPTZ DEFAULT now() NOT NULL` (trigger: set_updated_at)
- `workspace_id UUID NOT NULL REFERENCES workspaces(id)`
- `deleted_at TIMESTAMPTZ` (nullable, soft delete)

## Tables

### System
- **users**: id, email (unique), display_name, password_hash (argon2id), role (admin|standard), is_active
- **workspaces**: id, name, type (personal|shared), owner_id FK users
- **workspace_members**: id, workspace_id FK, user_id FK, role (admin|member). UNIQUE(workspace_id,user_id)
- **sessions**: id, user_id FK, refresh_token_hash CHAR(64) UNIQUE, device_info JSONB, expires_at, is_revoked

### Sources & Ingestion
- **sources**: id, workspace_id, name, type (local_folder|photo_folder|contacts|calendar|reminders), path, config_json, status (active|paused|error), last_sync_at, registered_by FK users
- **files**: id, workspace_id, source_id FK, filename, path, content_hash_sha256 CHAR(64), size_bytes, mime_type, metadata_json JSONB, is_duplicate, duplicate_of_id FK files
- **file_chunks**: id, file_id FK CASCADE, workspace_id, chunk_index INT, text_content TEXT, token_count INT, source_type (text|ocr), embedding_id. UNIQUE(file_id, chunk_index)
- **ingestion_states**: id, file_id FK UNIQUE, workspace_id, current_stage (DISCOVERED|FINGERPRINTED|METADATA_EXTRACTED|TEXT_EXTRACTED|OCR_COMPLETED|EMBEDDING_QUEUED|EMBEDDED|COMPLETED|FAILED|SKIPPED), stages_completed JSONB, error_message, retry_count (max 3)

### Imported Data
- **contacts**: id, workspace_id, source_id, external_id, first_name, last_name, display_name, emails_json, phones_json, addresses_json, organization, job_title, birthday, notes
- **calendar_events**: id, workspace_id, source_id, external_id, title, start_at, end_at, is_all_day, location, participants_json, recurrence_rule, calendar_name. UNIQUE(workspace_id, source_id, external_id)
- **reminders**: id, workspace_id, source_id, external_id, title, due_at, completed_at, is_completed, priority (high|medium|low|none), list_name, notes, write_through_status (pending|success|failed), created_by FK users

### Photo Intelligence
- **photo_assets**: id, file_id FK UNIQUE, workspace_id, taken_at, gps_lat, gps_lon, location_name, camera_make, camera_model, width, height, thumbnail_path, perceptual_hash CHAR(16), face_count
- **face_detections**: id, photo_asset_id FK, workspace_id, bbox_json, landmarks_json, embedding_encrypted BYTEA (pgcrypto), detection_confidence FLOAT, cluster_id FK face_clusters, qdrant_point_id
- **face_clusters**: id, workspace_id, representative_face_id FK, cluster_size INT, status (active|merged|split_source|noise), person_id FK trusted_persons, centroid_encrypted BYTEA

### People Graph
- **candidate_links**: id, workspace_id, source_type (face_cluster|contact|file|event), source_id UUID, target_type (contact|trusted_person), target_id UUID, confidence_score FLOAT, confidence_level (very_high|high|medium|low), evidence_json JSONB, status (pending|confirmed|rejected|deferred), reviewed_by FK users
- **trusted_persons**: id, workspace_id, display_name, canonical_contact_id FK contacts, trust_source (contact_import|face_confirmed|manual|merged), confirmed_at, confirmed_by FK users, merged_from_ids JSONB
- **graph_edges**: id, workspace_id, from_type, from_id, to_type, to_id, edge_type (co_photo|co_event|mentioned_in|contacted_by|associated_reminder), evidence_json, strength FLOAT. UNIQUE(workspace_id, from_type, from_id, to_type, to_id, edge_type)

### Generated
- **today_cards**: id, workspace_id, user_id FK, card_type, card_payload_json, priority_score FLOAT, source_ids_json, valid_from, valid_until, is_dismissed
- **pack_suggestions**: id, workspace_id, pack_id, suggestion_type, content_json, status (pending|accepted|dismissed|deferred), deferred_until
- **settings**: id, workspace_id, user_id, namespace, key, value_json. UNIQUE(workspace_id, user_id, namespace, key)

### Audit (append-only)
- **object_audit_log**: id BIGSERIAL, timestamp, user_id, workspace_id, action, object_type, object_id, old_state JSONB, new_state JSONB, metadata_json, source_ip INET. NO UPDATE/DELETE.

## Qdrant Collections
| Collection | Dim | Distance | Payload Indexes |
|---|---|---|---|
| document_embeddings | 768 (nomic-embed-text) | Cosine | workspace_id, file_id, source_id, chunk_index |
| photo_embeddings | 512 (CLIP) | Cosine | workspace_id, photo_asset_id, taken_at |
| face_embeddings | 512 (ArcFace) | Cosine | workspace_id, face_detection_id, cluster_id, person_id |

## Migration Rules
- Every migration has upgrade() AND downgrade(). Both tested.
- `make migrate` = alembic upgrade head. `make migration MSG="desc"` = create new.
- Schema changes require TL review.
