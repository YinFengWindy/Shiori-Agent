# Discover defects, then verify them

Review the current change for reachable failures. Acceptance of the requested behavior is a separate stage; the Windflow coordinator defines that split. The delivery caller owns review eligibility and merge gates. An explicit review request always runs.

## Pin the subject and assign coverage

Pin base and head, or an immutable snapshot including the exact uncommitted changes for a local review. Supply confirmed requirements, invariants, acceptance evidence, relevant investigation facts, and the design contract. Investigators can follow callers, state flow, history, and existing protections themselves. The implementer's claim that a path is safe is a claim to check.

Use independent defect discovery, not an implementer reviewing its own work. Start with one finder for bounded scope. Split larger work by behavior chains or risks when warranted; assign cross-slice interactions explicitly. Do not prescribe a universal number of agents or use model agreement as evidence.

Reviewers do not change the implementation. Put executable probes in an isolated scratch location or worktree. Preserve required repository standards and spec coverage as checks, not two mandatory reviewer identities.

## Discovery output

A finding supplies:
- A current supported operation, caller, external input, or actual system boundary that can trigger it.
- Trigger conditions and a reachable path through the exact code version.
- The invariant or requirement violated and the observable consequence.
- Existing protections considered and why they are insufficient.
- Source or runtime evidence, remaining assumptions, and severity separate from confidence.

Prefer a targeted reproduction when practical. Complete static control flow, types, or protocol contracts can also establish a defect. Failure to reproduce is not automatically a disproof; lack of contrary evidence is not confirmation.

An imagined future caller, hypothetical unsupported feature, or arbitrary violation of a proven internal contract is not by itself a present defect. Low frequency alone does not dismiss a reachable, consequential failure. No findings is valid; do not optimize for finding count.

## Independent verification

Deduplicate findings with the same root cause, preserving their evidence. A verifier distinct from the finder tests the claims. The parent may verify by actually tracing or probing the code; use a separate verifier when the parent authored the disputed change, cannot independently settle it, or the scope warrants it. Verification is a separate task, not a vote asking another model whether it agrees.

Actively look for counterevidence:
- Does the cited version contain this path?
- Can supported callers reach the state?
- Is an earlier validation, type, state machine, transaction, lifecycle rule, or ordering guarantee already sufficient?
- Does the reproduction demonstrate the claimed mechanism and user consequence?
- Does an external contract support the assumption, or is it conjecture?

If evidence lives outside the diff, inspect the relevant source rather than deleting a finding just because the diff omits it. Do not remove a confirmed requirement breach merely because it is inconvenient to reproduce.

Classify each finding as:
- **Confirmed defect:** causal evidence establishes a current failure.
- **Unresolved question:** name the missing fact and the bounded check needed.
- **Rejected finding:** give the concrete protection or counterevidence.
- **Future design suggestion:** outside current supported behavior; exclude from this patch by default.

A material evidence gap about a concrete current failure remains explicit and blocks claiming that affected behavior is verified. Generic hypothetical uncertainty does not create an endless review gate or justify defensive code.

## Check the necessity of the repair

A confirmed problem does not automatically validate the reviewer's proposed fix. Before adding a guard, fallback, retry, compatibility layer, or abstraction, explain:
- Which current behavior it protects.
- Why existing constraints cannot provide that protection.
- Why the failure belongs at this location rather than its source or an existing boundary.
- The added behavior and cost, including whether it hides invalid state.

Prefer correcting the cause, reusing an existing mechanism, or removing wrong logic. Do not add layers merely because an abnormal state can be imagined. A verified existing contract can justify no change. Product or compatibility changes return to the parent and, when material, the user.

## Report and repair

Report verified defects with evidence and the smallest necessary repair direction. Keep unresolved questions separate from confirmed problems. Summarize rejected findings and future suggestions without turning them into implementation tasks.

Only confirmed defects or material agreed requirement/standard violations enter authorized repairs. A review-only request stops at the report. When repairs are authorized, the parent assigns them and checks their actual scope. Revalidate previous findings and review newly changed behavior on the updated head. Preserve decisions backed by unchanged evidence and do not rerun equivalent checks without cause.

An unresolved confirmed defect or material acceptance gap prevents ready-for-merge. Independent review remains incomplete when the necessary reviewer capability is unavailable; do not label a self-review as completed independent discovery.
