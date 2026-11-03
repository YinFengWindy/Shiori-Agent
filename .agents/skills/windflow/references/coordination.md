# Agent ownership and communication

The parent maintains the user's intent, current decisions, and overall design. Delegation assigns bounded work; it does not transfer product authority or expand authorization.

## Authority

These three rules are the collection's source of truth. Stage skills keep a one-line pointer and their own actions.

- **Acceptance is not review.** Acceptance checks whether the agreed behavior works. Review asks where the current behavior can still fail, and whether a proposed repair is necessary. Keep the two results separate. A hypothetical warning does not become defensive code.
- **Silence and green CI are not approval.** The user confirms requirements, the ticket breakdown, and merging the finished PR. A quiet thread, a passing check, or a successful command does not grant those confirmations. An explicit authorization already on record stays in force for that same action.
- **The parent owns product decisions.** The parent keeps context and design revisions, integration, Git and tracker actions, and questions to the user. Workers report contradictions with evidence. Technical adjustments inside the agreed scope stay with the parent. Material product changes return to the user.

## Roles

| Role | Responsibility |
| --- | --- |
| Parent | Read investigation evidence, grill the user, compare design proposals, converge the design, approve technical adjustments, integrate, manage Git/tracker/CI, and obtain user confirmations. |
| Investigator | Use current behavior or historical rationale to answer concrete factual questions, with source evidence and unknowns. |
| Design candidate | Independently propose a solution to the same confirmed problem. Do not inspect another candidate's unfinished proposal. |
| Implementer | Implement an approved ticket against the current design in the assigned workspace; run focused checks and report results or contradictions. |
| Finder | Independently search current behavior chains for defects in a fixed change. |
| Verifier | Challenge each finding's mechanism and the necessity of its proposed fix, using the review skill. |

Only the parent asks user-facing product questions. Workers do not widen scope, publish issues, commit, push, change branches, merge, or contact other people. Use native agent tools and the host's configured model defaults. Do not invent unavailable model families, cloud workers, messaging integrations, or user-visible chats.

## Share evidence, not just a summary

Before design comparison and implementation, provide a versioned context packet. Reuse the spec and existing investigation records by reference; small tasks need no separate document.

- Confirmed goal, observable acceptance criteria, exclusions, and the reasons behind material user decisions.
- Repository, exact baseline, relevant source entrypoints, call/state flows, and source-backed historical constraints.
- Facts, inferences, remaining unknowns, and rejected directions with their reasons.
- Current design and contract revision when available.
- Assignment, output location, applicable instructions, writable boundaries, and verification responsibilities.

Keep primary evidence accessible: source paths and revisions, linked issues/ADRs, relevant commands and outputs. Include fetched excerpts when a child cannot access the source. A summary is an index, not the sole source of truth.

Conversation inheritance can supplement the packet when the host supports it. Explicitly identify the latest decisions so discarded drafts cannot override them. Inheriting the parent's history does not reproduce an investigator's entire context. Workers may read original evidence and request missing context.

## Coordinate questions through the parent

An investigator can be reused through the clarification loop when accumulated context is useful. Fresh design candidates work from the same frozen packet and produce their own proposal and rationale. The parent judges their outputs and performs architectural convergence.

When a worker finds an evidence gap or design contradiction, send the parent:
- The exact question or contradiction and its source.
- Which assigned behavior is affected.
- What was checked, and what observation would resolve it.
- Whether independent work can continue.

The parent routes factual follow-ups to investigators. It resolves technical details within scope, returns product changes to the user, updates the context revision, and notifies affected workers. Pause only work invalidated by the change. Workers must not silently revise the contract or negotiate a new product decision among themselves.

## Isolate writes and integrate

Default to one implementer per approved unblocked ticket. An isolated worktree is the default for orchestrated and parallel implementation. Use the workspace the user names when they specify one. Implement on the target or default branch only when the user assigns that workspace.

Name the branch from the repository's convention or the name the user requests. Do not hardcode a `codex/` prefix.

Parallelize only independent scopes, with explicit integration ownership and separate writable worktrees. Read-only investigation can share a checkout when no writer is changing its baseline.

Preserve unrelated work. If the task depends on uncommitted user edits, account for them explicitly. Do not omit, stage, stash, reset, or publish them silently. Stage only this task's changes. Run the repository's pre-commit checks before committing.

The implementer returns its workspace and baseline, changed files, acceptance evidence, commands and results, unrun checks, and design deviations. The parent checks the actual diff and evidence before Git or tracker mutations. A success statement alone is not enough. Reuse successful checks unless a material change or a gap requires more verification.

Wait for writers and running mutation commands before staging, changing branches, or starting review on that checkout. Review runs on a pinned snapshot. Reproduction scripts belong in a separate scratch/worktree location, not in the implementation tree.

Send repairs back to the existing implementer when its state remains useful. A replacement receives the current packet, workspace state, prior findings, and dispositions. Every agent result records its context revision and code baseline.

## Capability fallback

If investigation or implementation agents are unavailable, disclose that the parent is doing that work and continue within scope. If design cannot run independent candidates, report that comparison as limited; do not describe one serial answer as independent alternatives. The parent can prepare a design, while any unresolved material choice remains explicit.

If required independent discovery cannot run, review remains pending. Complete other preparation without claiming the review gate passed. Never create user-visible tasks or external messages just to emulate missing subagents.
