# Routers

FastAPI route handlers. Each file maps to an API resource (e.g., `auth.py`, `search.py`).

All endpoints (except `/health` and `/auth/login`) require `Depends(get_current_user)`.
