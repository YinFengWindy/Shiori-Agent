---
name: ship
description: "Prepare or finish delivery of an implemented change through PR, CI, review evidence, authorized merge, and branch cleanup. Use for opening PRs, fixing delivery blockers, or shipping completed work."
metadata:
  collection: windflow
---

# Ship

Deliver an existing change to the stopping point the user requested: a PR, CI evidence, review evidence, or an authorized merge. Read [delivery](references/delivery.md) for those gates and for cleanup. Branch setup, worktree isolation, and pre-commit checks belong to implementation.

Silence and green CI are not approval, and acceptance is not review. The Windflow coordinator defines those rules. Publish and check the change that already exists, and merge only after an explicit confirmation of this PR and head.

Inspect live Git, PR, CI, acceptance, review, and authorization state. Reuse existing artifacts and reconcile uncertain remote operations before retrying. Do not backfill a requirements interview or publish a new ticket set for a standalone delivery request.

Accept implementation and acceptance evidence from the user or an earlier stage. Obtain missing facts through repository or provider tools. When required review is absent, obtain an actual independent review if the review skill or an equivalent process is available; otherwise report the gate as pending.

Keep the source branch, head, base, check results, review result or recorded exemption, user approval, and provider state explicit. A successful command or a queued merge is not a merged result.

In an orchestrated run, report evidence to the parent. Change branches, publish, or merge only when the brief assigns that action. Product decisions stay with the parent. Direct invocation follows the user's actual authorization.

Do not disable checks, bypass provider approvals, force-push shared branches, or execute a separate production deployment to finish delivery. Preserve useful independent progress when a gate is blocked.
