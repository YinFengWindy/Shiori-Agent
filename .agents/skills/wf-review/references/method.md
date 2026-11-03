# Discover defects, then verify them

## Discovery

Use a finder that did not write the change; an implementer reviewing its own work is not independent discovery. One finder is enough for a bounded change; split larger ones by behavior or risk and give someone the interactions between slices. Probes and reproduction scripts go in a scratch location, not the implementation tree.

A finding has to name a real trigger and trace it through the pinned code:

- What current, supported input or caller triggers it, and the path it takes.
- What requirement or invariant breaks, and what the user or system observes.
- Which existing protections were considered, and why they don't stop it.
- The evidence, the remaining assumptions, and severity kept separate from confidence.

An imagined future caller or an unsupported feature is not a present defect. Rarity alone does not dismiss a reachable, consequential failure. Zero findings is a valid result.

```text
Confirmed defect: duplicate write on retry (severity high, confidence high)
Trigger: the user saves while offline, then reconnects. This is a supported flow.
Path at 9f8e7d6: queue.flush -> saveDoc -> withRetry -> POST /docs/:id.
  flush creates a new Idempotency-Key on every attempt (src/sync/queue.ts:57).
Violates: "the server receives each queued edit once" (ticket acceptance criterion 2).
Protections checked: server dedupe keys on Idempotency-Key, so it cannot catch this.
Evidence: a scratch test returns 503 once; the server records 2 inserts.
Repair direction: create the key when the edit is queued and reuse it on every attempt. No new retry layer.
```

## Verification

Merge findings that share a root cause, then verify each one separately from the finder. The point is to look for counterevidence, not to ask another model whether it agrees. Check whether the path exists in this version, whether supported callers can reach it, whether an earlier validation, type, transaction, or ordering guarantee already prevents it, and whether the reproduction really shows the claimed mechanism. The agent running the review may do this itself, unless it wrote the disputed code.

Classify each finding:

- **Confirmed defect:** the evidence establishes a current failure.
- **Unresolved question:** name the missing fact and the check that would settle it.
- **Rejected:** cite the protection or counterevidence.
- **Future suggestion:** outside current supported behavior; not part of this patch.

## Is the repair necessary?

A confirmed problem does not validate the proposed fix. Before adding a guard, fallback, retry, compatibility layer, or abstraction, say what current behavior it protects, why the existing constraints do not, and why the fix belongs here rather than at the source. Prefer fixing the cause, reusing an existing mechanism, or deleting wrong logic. A verified existing contract can mean no change at all. Take product or compatibility changes to the user.

## Report

Report confirmed defects with evidence and the smallest repair direction. Keep unresolved questions apart from them, and list rejected findings and future suggestions briefly, without turning them into tasks. Only confirmed defects and real requirement or standard violations go into repairs. After repairs, recheck the earlier findings and review the newly changed behavior.

An unresolved confirmed defect blocks ready-for-merge. If independent review could not run, say it is incomplete; do not label a self-review as independent.
