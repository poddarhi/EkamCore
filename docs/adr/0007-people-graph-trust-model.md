# ADR 0007: People Graph Trust Model

- Status: Accepted
- Date: 2026-03-15
- Owners: EkamCore engineering
- Related Sprint tasks: Sprint 6 graph implementation work
- Related docs: `/Users/hiteshpoddar/EkamCore/docs/adr/0004-workspace-scoping.md`

## Context

People Graph is central to EkamCore's value, but it carries real trust risk. The product docs are explicit that uncertain identity suggestions must not silently become trusted truth. The graph needs candidate state, trusted state, and user-review flows that preserve confidence boundaries.

## Decision

EkamCore uses a conservative People Graph trust model with at least three distinct states: machine-generated candidates, reviewable candidate links, and trusted person state. Uncertain links stay in candidate or review surfaces until a trusted path confirms them.

## Decision Drivers

- Relationship intelligence is valuable only if users can trust it.
- Photo and identity suggestions are inherently probabilistic.
- The system must preserve user-confirmed trust decisions differently from rebuildable derived artifacts.

## Consequences

### Positive

- Gives People Graph a usable but reviewable path into the product.
- Aligns graph behavior with export and restore expectations for trusted state.

### Tradeoffs

- Review queue design and prioritization become important early.
- Some suggestions will surface later or more softly than a more aggressive graph system would allow.

## Alternatives Considered

### Auto-Promoting High-Confidence Suggestions

- Considered as a way to make the graph feel smarter faster.
- Rejected because it increases the chance of incorrect trusted identity state and undermines user trust.

### Binary Trusted / Not Trusted Model Only

- Considered as a simpler state model.
- Rejected because it does not represent provisional evidence and reviewable suggestions well enough.

## Follow-up Work

- Define candidate-link review operations such as merge, split, confirm, and undo.
- Define queue prioritization so large libraries do not produce unmanageable suggestion volume.
- Clarify export boundaries for confirmed identity decisions versus rebuildable clustering artifacts.

## Notes

Implementation details for queue mechanics and evidence weighting still need a dedicated technical design note.
