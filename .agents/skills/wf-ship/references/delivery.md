# Delivery gates

## Commit and PR

Deliver the branch that implementation produced. If task changes are still uncommitted, commit them first; the request to ship authorizes that. If they sit on the default branch, move them to a task branch first. Stage only this task's files and run the repository's pre-commit checks. In a coordinated run, the coordinating agent does this. Stop and ask if the task's changes can't be separated from unrelated edits, or if task commits are already on the local default branch.

Keep one ticket per PR unless tickets genuinely cannot land separately. Describe the behavior change, the verification, and the spec or ticket links. Use closing references only for tickets this PR fully completes.

## CI

CI counts only if it ran on the current PR head, or on the provider's merge candidate for it. Work out which checks are expected from the workflows and branch rules. A missing, pending, cancelled, or failed expected check is not a pass, and a skipped one passes only if the workflow's own rules say it doesn't apply. Diagnose failures before rerunning them; rerun only failures that are evidently transient.

## Review

Every PR is reviewed before merge, whatever its size. Run wf-review, or the repository's own review process if wf-review is not installed, on the pinned PR head, after CI. The finder must be independent of the implementer, and each finding must be verified separately. Send confirmed defects back to implementation, and apply wf-review's necessity check before adding guards or layers. After a fix, collect fresh CI, recheck the earlier findings, and review the newly changed behavior. A review that can't run stays pending, and so does the merge. Agent review does not replace required human or Code Owner approval.

## Merge

When the scope is implemented and accepted, CI on the head is green, review is done, and provider rules are satisfied, show the user:
- the PR URL and the branches;
- the head SHA;
- what changed;
- CI and review results;
- anything with consequences.

Then wait for an explicit confirmation of that PR and head. Requirement or ticket approval does not count. Once confirmed, do not ask again for the same unchanged head. For several PRs, get approval that names each one.

Re-read the head and gate status just before merging. A new head needs fresh CI, a review of what changed, and a new confirmation. Merge with the provider's expected-head guard when one exists (GitHub: `gh pr merge --match-head-commit`), using the repository's usual merge method. Never use admin bypass. Do not enable auto-merge that could carry this approval to a later head. Confirm the provider reports `MERGED` before saying so. Close tickets only when their behavior is fully delivered.

## Branch and worktree cleanup

The merge confirmation also authorizes cleaning up after the PR once the provider reports `MERGED`:

- **Remote branch:** delete it if its tip still equals the merged head. Do not delete a default, protected, or integration branch, or one that another open PR still uses.
- **Task worktree:** if a worktree was created for this task, has the merged source branch checked out, has no uncommitted or untracked changes, and holds no commits beyond the merged head, remove it with `git worktree remove` (without `--force`). Leave the main checkout, the worktree you are running in, and worktrees the host app manages for its sessions; report those instead.
- **Local branch:** delete it once no worktree has it checked out and it holds no commits beyond what was merged. A squash merge can make an ancestry check fail even when nothing would be lost, so compare against the merged head.

Leave other worktrees and uncommitted work alone. If cleanup fails, report "merged; cleanup pending" and do not merge again.

## Blockers

A timeout after creating an issue or PR, or after merging, may hide a success, so query the remote before retrying. If the same blocker survives diagnosis, stop and report it with a concrete next step instead of looping. A pause, a revoked instruction, or a scope change takes effect immediately.
