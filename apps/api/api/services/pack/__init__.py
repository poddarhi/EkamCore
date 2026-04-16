"""Pack infrastructure module (S14-001 / S14-002).

Holds the manifest loader, capability registry, and (in later
stories) the sandboxed execution context. Imports are lazy via
submodules so a FastAPI startup that skips packs entirely doesn't
pay the cost.
"""
