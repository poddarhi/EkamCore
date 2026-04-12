"""FastAPI dependency helpers (S11-002+).

Each module in this package exports callables suitable for FastAPI's
Depends(). Depencies here are stateless wrappers over services; they
do NOT contain business logic.
"""
