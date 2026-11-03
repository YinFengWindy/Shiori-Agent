---
name: wf-implement
description: "Implement an agreed behavior or approved ticket on an isolated task branch, against its design, with focused local checks. Use when the behavior is settled and the change is real feature work, a scoped fix, or an evidence-backed repair."
metadata:
  collection: windflow
---

# Implement

Turn the agreed behavior and design into a scoped code change. A ticket, spec, or clear instruction is enough; no other skill is required. Ask the user only about product intent, meaning what users see or can do, what data is kept, compatibility, or scope. Decide technical details yourself.

## Workspace

Work on a task branch, not the target or default branch, unless the user assigns that branch.

- **Assigned by a coordinating agent:** use the worktree and branch it gives you.
- **Named by the user:** use that workspace.
- **Otherwise:** if you are already on a task branch for this work, continue there. If not, create an isolated worktree and branch, named by the repository's convention.

Uncommitted edits that are not yours belong to the user. Leave them alone, and if your change depends on them, say so.

## Change and check

For a bug, confirm the failure before fixing it, and recheck the original scenario afterwards. Add a regression test where one can actually catch the bug.

Run focused checks for what you touched and its callers, rather than the whole local suite by default; required CI still runs. Never weaken a test or check to get a pass. If the design turns out to be wrong, report what broke and why instead of quietly working around it.

## Commit

- **Assigned by a coordinating agent:** leave committing to it. It reviews your diff and commits.
- **Direct invocation:** commit when the user asked for a commit, a PR, or delivery. Otherwise leave the changes uncommitted and say so.

To commit, stage only this task's files, run the repository's pre-commit checks, and commit on the task branch.

## Return

```text
Workspace: ../wt/offline-queue (branch feat/offline-queue, base main@a1b2c3d)
Changed: src/sync/queue.ts, src/store/doc.ts, test/sync/queue.test.ts
Acceptance:
- Offline edit survives reload: met. queue.test.ts "persists across reload" passes.
- Queued edits are sent once, in order: met. queue.test.ts "flushes in order" passes.
Commands: npm test -- sync/queue (12 passed); npm run typecheck (ok)
Not run: e2e suite, needs staging credentials
Deviations from design: none
Commit: none; the coordinating agent commits
```

Stop at the requested outcome. Finished code is not a request to open a PR or merge.

Parallel-work isolation draws on pstack `swarm` by Lauren Tan (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
