"""Pack capability registry (S14-002 / ART-13 §4).

Every access a pack performs — reading a table, traversing the
graph, invoking an LLM — goes through one of these named
capabilities. The registry is the canonical enumeration; the
manifest loader rejects any capability a pack declares that
isn't listed here, and the (S14-003) PackContext strips
consent-gated capabilities at runtime whenever
``face_pipeline_active`` is False for the workspace.

Design rules (ART-14 threat model):

  1. **Capability names are stable identifiers.** ``read:contacts``,
     not ``contact_read``. The ``scope:target`` shape lets the
     runtime derive coarse ACL rules without parsing strings each
     call.
  2. **Consent-gated = face pipeline required.** Anything that
     traverses trusted_persons or graph_edges (with a person from
     or to) is flagged ``requires_consent=True``. The runtime
     *silently* degrades — strips the capability from the
     effective set — rather than raising, so a user who revokes
     consent mid-run sees the pack produce fewer cards instead of
     a hard failure.
  3. **Writes are explicit.** The one write capability
     (``write:reminders``) is the only way a pack can mutate user
     data. Every other capability is read-only by construction.
  4. **Unknown capabilities fail closed.** ``get()`` returns None
     for unknown names; the manifest loader treats None as a
     validation error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


CapabilityScope = Literal["read", "write", "query", "invoke"]
CapabilityTarget = Literal[
    "contacts",
    "calendar_events",
    "reminders",
    "trusted_persons",
    "graph_edges",
    "graph",
    "llm",
    "files",
    "photos",
]


@dataclass(frozen=True)
class CapabilityDef:
    name: str
    description: str
    data_scope: CapabilityScope
    target: CapabilityTarget
    requires_consent: bool


CAPABILITY_REGISTRY: dict[str, CapabilityDef] = {
    "read:contacts": CapabilityDef(
        name="read:contacts",
        description="Read rows from the contacts table.",
        data_scope="read",
        target="contacts",
        requires_consent=False,
    ),
    "read:calendar_events": CapabilityDef(
        name="read:calendar_events",
        description="Read rows from the calendar_events table.",
        data_scope="read",
        target="calendar_events",
        requires_consent=False,
    ),
    "read:reminders": CapabilityDef(
        name="read:reminders",
        description="Read rows from the reminders table.",
        data_scope="read",
        target="reminders",
        requires_consent=False,
    ),
    "read:trusted_persons": CapabilityDef(
        name="read:trusted_persons",
        description=(
            "Read rows from the trusted_persons table. Requires "
            "face consent because trusted persons are derived "
            "from biometric clusters."
        ),
        data_scope="read",
        target="trusted_persons",
        requires_consent=True,
    ),
    "read:graph_edges": CapabilityDef(
        name="read:graph_edges",
        description=(
            "Read rows from the graph_edges table. Requires face "
            "consent because many edges carry trusted_person ids."
        ),
        data_scope="read",
        target="graph_edges",
        requires_consent=True,
    ),
    "read:files": CapabilityDef(
        name="read:files",
        description="Read rows from the files table.",
        data_scope="read",
        target="files",
        requires_consent=False,
    ),
    "read:photos": CapabilityDef(
        name="read:photos",
        description="Read rows from the photo_assets table.",
        data_scope="read",
        target="photos",
        requires_consent=False,
    ),
    "write:reminders": CapabilityDef(
        name="write:reminders",
        description=(
            "Create reminders via the write-through pipeline. "
            "The only write capability a pack may declare."
        ),
        data_scope="write",
        target="reminders",
        requires_consent=False,
    ),
    "query:graph": CapabilityDef(
        name="query:graph",
        description=(
            "Traverse graph_edges with depth. Requires face "
            "consent because the traversal visits person nodes."
        ),
        data_scope="query",
        target="graph",
        requires_consent=True,
    ),
    "invoke:llm": CapabilityDef(
        name="invoke:llm",
        description=(
            "Call the local LLM via the resource controller. "
            "Rate-limited by the pack manifest's "
            "max_llm_calls_per_run."
        ),
        data_scope="invoke",
        target="llm",
        requires_consent=False,
    ),
}


def get(name: str) -> CapabilityDef | None:
    """Return the definition for ``name`` or None if unknown.

    Used by the manifest validator to reject unknown capabilities
    at load time and by the pack runtime to look up consent gating
    at access time.
    """
    return CAPABILITY_REGISTRY.get(name)


def consent_gated_capabilities() -> frozenset[str]:
    """Return every capability name whose definition requires
    active face consent. Computed once; returned as a frozenset so
    callers can treat it as immutable."""
    return frozenset(
        name for name, defn in CAPABILITY_REGISTRY.items() if defn.requires_consent
    )
