# S08-002: Photo Search by Metadata — Design Spec

**Date:** 2026-04-09  
**Story:** S08-002 — Search photos by date, location, and camera  
**Phase:** 2 (Sprint 8)  
**Workstream:** backend  
**Depends on:** S08-001 (photo_assets table must exist)  
**Status:** Approved

---

## Context

S08-001 ingests photos into the `photo_assets` table with EXIF metadata (dates, GPS, camera). S08-002 makes that metadata searchable — extending the existing `/api/v1/search` endpoint with `type='photo'` and adding three deterministic query patterns so natural-language queries like "photos from last week" route to fast SQL without an LLM.

Photos have no text body, so this is **metadata-only SQL search** (no Qdrant, no embeddings). CLIP visual embeddings land in a later sprint.

---

## Architecture

```
GET /api/v1/search?type=photo&q=Paris&date_from=...
          │
          ▼
search_all("photo", filters) in query/search.py
          │
          ▼
search_photos(workspace_ids, query, filters, limit, offset, db)
          │                         in services/search/photo_search.py
          ▼
SELECT FROM photo_assets
  WHERE workspace_id = ANY(:ids)
    AND deleted_at IS NULL
    AND taken_at BETWEEN date_from AND date_to     (if set)
    AND location_name ILIKE '%term%'               (if set)
    AND (camera_make || ' ' || camera_model) ILIKE '%cam%'  (if set)
    AND gps_lat IS NOT NULL                        (if has_gps=true)
    AND (location_name ILIKE '%q%' OR camera_make ILIKE '%q%' ...)
ORDER BY taken_at DESC NULLS LAST
LIMIT limit OFFSET offset
          │
          ▼
list[PhotoCard]  +  total_count (for facets)
```

---

## Files to Create

| File | Purpose |
|---|---|
| `apps/api/api/services/search/photo_search.py` | Core search function |
| `apps/api/tests/test_photo_search.py` | Unit + integration tests |

## Files to Modify

| File | Change |
|---|---|
| `apps/api/api/services/query/search.py` | Add "photo" to SearchType, dispatch to photo_search, add has_gps param |
| `apps/api/api/routers/search.py` | Add "photo" to type literal, add has_gps query param |
| `apps/api/api/services/query/patterns.py` | Add photo_date, photo_location, photo_camera IntentTypes + patterns |
| `apps/api/api/services/query/router.py` | Add handlers for three new intent types |

---

## Service Design: photo_search.py

```python
@dataclass(frozen=True)
class PhotoFilters:
    date_from: datetime | None = None
    date_to: datetime | None = None
    location_contains: str | None = None   # ILIKE on location_name
    camera: str | None = None              # ILIKE on make || ' ' || model
    has_gps: bool | None = None

async def search_photos(
    workspace_ids: list[UUID],
    query: str,                            # free-text; empty = no text filter
    filters: PhotoFilters,
    limit: int,
    offset: int,
    db: AsyncSession,
) -> tuple[list[PhotoCard], int]:          # (cards, total_count)
```

**PhotoCard payload:**
```python
{
    "photo_id": str(photo.id),
    "thumbnail_url": f"/api/v1/photos/{photo.id}/thumbnail",
    "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
    "location_name": photo.location_name,
    "camera": f"{photo.camera_make or ''} {photo.camera_model or ''}".strip() or None,
    "width": photo.width,
    "height": photo.height,
}
```

**Query construction rules:**
- Always include `workspace_id = ANY(:ids)` and `deleted_at IS NULL`
- `taken_at BETWEEN` only when both `date_from` and `date_to` are set; `>= date_from` or `<= date_to` if only one is set
- All ILIKE patterns use `%term%` (contains), case-insensitive
- `q` free-text is OR'd across `location_name`, `camera_make`, `camera_model`
- No JSONB queries needed — all filter columns are direct columns on `photo_assets`
- `ORDER BY taken_at DESC NULLS LAST` (most recent first)

---

## Router Integration

### search.py (router)

Add to `type` Literal: `"photo"` alongside existing `"calendar" | "reminder" | "contact" | "file"`.

Add query param: `has_gps: bool | None = Query(None)`.

### query/search.py (search aggregator)

```python
# Add to SearchType
SearchType = Literal["calendar", "reminder", "contact", "file", "photo", "all"]

# Add has_gps param to search_all()
async def search_all(
    query: str,
    workspace_id: UUID,
    db: AsyncSession,
    *,
    types: list[SearchType] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    has_gps: bool | None = None,     # NEW
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Card], dict[str, int]]:
    ...
    if "photo" in resolved_types:
        filters = PhotoFilters(
            date_from=date_from,
            date_to=date_to,
            has_gps=has_gps,
        )
        photo_cards, photo_total = await search_photos(
            workspace_ids=[workspace_id],
            query=query,
            filters=filters,
            limit=limit,
            offset=offset,
            db=db,
        )
        all_cards.extend(photo_cards)
        facets["photo"] = photo_total
```

---

## Deterministic Query Patterns

Three new `IntentType` values added to `patterns.py`:

### `photo_date`
```
Pattern: r"photos?\s+from\s+(?P<date_ref>yesterday|today|last week|last month|this week|this month|\d{4})"
Examples: "photos from last week", "photo from 2024", "photos from yesterday"
Extracts: date_ref
```

### `photo_location`
```
Pattern: r"photos?\s+(?:in|from|near|at)\s+(?P<location>.+)"
Examples: "photos in Paris", "photos from Tokyo", "photos near home"
Extracts: location
```

### `photo_camera`
```
Pattern: r"photos?\s+(?:with|taken with|from|shot with)\s+(?P<camera>.+?)(?:\s+camera|\s+phone|\s+iphone)?"
Examples: "photos with iPhone", "photos taken with Canon", "photos from Nikon camera"
Extracts: camera
```

Handlers in `router.py`:
- `_handle_photo_date`: parse `date_ref` via existing `_parse_date_ref()`, call `search_photos()` with date range
- `_handle_photo_location`: call `search_photos()` with `filters.location_contains`
- `_handle_photo_camera`: call `search_photos()` with `filters.camera`

All return `ResponseEnvelope` with `cards=photo_cards`, `confidence_level="deterministic"`.

---

## Tests: test_photo_search.py

| Test | Scenario |
|---|---|
| `test_date_range_filter` | Photos outside date range excluded |
| `test_date_from_only` | Only lower bound; future photos included |
| `test_location_filter_ilike` | "paris" matches "Paris, Île-de-France, FR" |
| `test_camera_filter_make_model` | "canon" matches camera_make="Canon", model="EOS R5" |
| `test_has_gps_filter_true` | Only photos with gps_lat IS NOT NULL |
| `test_has_gps_filter_false` | Only photos with gps_lat IS NULL |
| `test_combined_date_location` | date_from + location together |
| `test_workspace_isolation` | Photo from other workspace excluded |
| `test_free_text_or_logic` | q="Paris" matches location_name OR camera_make |
| `test_type_photo_routes_search_all` | type='photo' in search_all dispatches correctly |
| `test_photo_date_pattern` | "photos from last week" → QueryIntent(photo_date, date_ref="last week") |
| `test_photo_location_pattern` | "photos in London" → QueryIntent(photo_location, location="London") |
| `test_photo_camera_pattern` | "photos with iPhone" → QueryIntent(photo_camera, camera="iPhone") |

---

## Verification

```bash
cd apps/api && poetry run pytest tests/test_photo_search.py -v
make test-api
```

Smoke test: `GET /api/v1/search?q=Paris&type=photo&workspace_id=<uuid>` → 200 with PhotoCards or empty data=[].
