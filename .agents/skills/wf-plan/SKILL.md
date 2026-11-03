---
name: wf-plan
description: "Turn agreed requirements and a design into a written spec and issue-tracker tickets with acceptance criteria and dependencies. Use for drafting a spec, proposing a ticket breakdown, or publishing an approved one."
metadata:
  collection: windflow
---

# Plan

Produce a spec, a ticket breakdown, or both, as requested. Inputs can come from earlier stages or straight from the user.

## Spec

Record the problem, the intended behavior, observable acceptance criteria, exclusions, key design decisions with their reasons, and how it will be verified. Link evidence instead of copying it, and size the document to the work. A spec is not ready while a product decision is still missing; name the missing decision.

## Check for overlap once

After drafting a spec you intend to publish, search the target repository's open and closed issues once for the same behavior. If something plausibly overlaps, show the user the candidates and your recommendation, and let them choose to reuse, extend, create separately, or drop. If you could not search fully, say so; it is not proof of no duplicates.

Skip this when the user supplied the issue to implement, or only wants a local draft.

## Tickets

Each ticket is a slice of behavior that can be accepted on its own, not a technical layer. It carries its behavior, acceptance criteria, exclusions, and real blockers.

```text
Title: Queue edits while offline and sync on reconnect
Spec: #301    Design: docs/offline.md @ 4c5d6e7    Blocked by: none
Behavior: edits made offline are saved locally and sent in order after reconnecting.
Acceptance:
- With the network off, an edit survives a page reload.
- After reconnecting, the server receives each queued edit once, in order.
Excludes: conflict UI (#303).
```

Show the breakdown and get approval before publishing tickets or starting implementation. For a single ticket, present the requirement and the ticket together and ask once. Changes to scope or splitting need renewed agreement. Implementing one existing ticket needs no new breakdown.

## Publish

For authorized full delivery, publish the spec, then the approved tickets in dependency order. A small change can use one issue as both spec and ticket, but it still gets an issue before implementation; clear requirements skip the interview, not the issue. A blocker counts as resolved when its behavior exists, not merely when its issue is closed.

Return what was written and published, the overlap decision, and the approvals on record. A planning request stops there.

Adapted from Matt Pocock's `to-spec` and `to-tickets` (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
