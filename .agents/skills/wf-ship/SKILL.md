---
name: wf-ship
description: "Publish an implemented change as a PR, drive its CI and any required review, merge only after explicit approval of that PR, then clean up the branch and task worktree. Use for opening PRs, fixing delivery blockers, or merging finished work."
metadata:
  collection: windflow
---

# Ship

Take an existing change as far as the user asked: a PR, green CI, review evidence, or a merge. Read [delivery](references/delivery.md) for the gates.

Three rules hold throughout:

- **Approval is explicit.** Silence, green CI, or a successful command is not approval. Merge only after the user confirms this specific PR and head.
- **Acceptance and review are different checks.** Acceptance asks whether the agreed behavior works; review asks where the change can still fail. Neither stands in for the other.
- **Stay at the requested stop.** A request for a PR or for CI does not include permission to merge.

Start from the live state of Git, the PR, and CI, and reuse what already exists. A standalone delivery request does not need a requirements interview or new tickets. When a coordinating agent assigned this work, report to it and take only the actions the brief assigns.

Do not disable checks, bypass required approvals, force-push shared branches, or run production deployments to get a change through.
