# Delivery Gates

Read this reference when publishing, checking, merging, or cleaning up a change that already exists. Apply the user's requested stopping point throughout; a review-only or CI-only entry does not inherit permission to merge.

Acceptance is not review, and silence or green CI is not approval. The Windflow coordinator states those rules. This file covers PR, CI, the review gate, merge, and cleanup. Branch naming, worktree setup, and pre-commit checks belong to implementation.

## Branch and PR

Deliver the branch and commits implementation already produced. Do not create an implementation worktree or choose a branch name from this stage.

- Fetch the relevant base and inspect the current branch, worktree, and any existing PR. Continue that task branch and PR. If the change has no branch yet, is still on the target or default branch, or still has uncommitted task changes, stop and return it to implementation. Implementation owns the branch, the commit, and the repository's pre-commit checks.
- Keep one independently landable ticket per PR. Use an integration branch only when tickets genuinely cannot land green separately. Track its final integration PR. An intermediate branch merge is not delivery to the intended target.
- Push the existing commits and create or update a draft PR with the behavior change, verification, and spec or ticket links. Use closing references only for tickets this PR fully completes. A partial ticket PR must not close the parent feature.
- Use structured tool arguments for multiline bodies. For CLI publication, write the exact text with the available file-edit tool and pass `--body-file` (or the provider equivalent). Verify repository, base, head, URL, and returned status after creation.

## CI

- Return confirmed repairs to the implementer and wait until writers finish before the next Git mutation or review on that checkout.
- Inspect workflows, scripts, and remote branch or ruleset requirements to determine expected CI. Required policy checks and the repo's documented delivery gates both matter, even if branch protection is absent.
- Record the pushed PR head SHA. Verify CI belongs to that head, or to the provider's corresponding PR merge candidate. A successful run on the base branch or a previous head does not count.
- Account for expected checks explicitly. An empty check list, a missing expected job, a pending or cancelled run, or a failed run is not success. Accept skipped or not-applicable results only when the workflow's applicability rules justify them for this change. An optional neutral result cannot substitute for an expected validation job.
- If draft status prevents required CI from running, mark the PR ready once implementation's checks have passed. Merge stays gated on CI and any required review. Read failures and return the repair to implementation, which runs the repository's pre-commit checks before the next commit. After the new head is pushed, collect fresh CI.
- Use bounded polling with backoff and updates. Do not blindly rerun a deterministic failure. A rerun is appropriate for a demonstrated transient infrastructure failure. Repeated identical external failures need a diagnosis or a concrete blocker report.

## Decide whether review is needed

After inspecting the actual PR diff, skip the automatic review stage when either exemption applies:

| Change | Review decision |
| --- | --- |
| Small feature: a bounded behavior change with local impact and straightforward acceptance criteria, such as a filter option or an existing workflow's small convenience action | Skip automatic code review. |
| UI-only: layout, styling, copy, icons, responsive behavior, or client-side presentation interactions, without changes to backend behavior or business contracts | Skip automatic code review, even when many UI files change. |
| Mixed UI and substantive non-UI changes, shared contract/architecture changes, broad refactors, or changes to permissions, auth, billing, persistence semantics, or data deletion | Run code review; a small line count or UI component location alone is not an exemption. |
| The user explicitly requests a review | Run the requested review regardless of size or UI scope. |

A mixed change may still qualify as a small feature when its entire behavior is bounded and none of the substantive cases above applies. Judge impact and behavior, not file count. Decide from repository evidence without adding a routine user confirmation. If the diff cannot be classified confidently, run review and briefly explain why.

Record `skipped: small feature` or `skipped: UI-only`, the short reason, and the head and base evaluated. Do not invoke review subagents for an exempt change or label a skipped review as passed. Reassess eligibility after each new commit or changed base so a later high-impact change does not inherit an obsolete exemption.

Review exemption changes only this agent review stage. Run the repository's applicable checks and CI, verify the affected behavior, and keep the user merge checkpoint. For UI changes, validate the rendered result and relevant interactions using the repository's existing visual/accessibility practices. Required provider approvals and protections still apply.

## Review after CI (when required)

1. Pin the current PR base/head. Supply the confirmed requirements, design contract, source evidence, and acceptance results to independent reviewers. Use the Windflow review skill when installed; otherwise obtain review through the repository's available review process. A missing required review remains pending.
2. Assign independent defect discovery on the fixed snapshot. Partition by affected behavior when needed; cover cross-slice interactions. Standards and requirements remain checks, not fixed reviewer identities.
3. Have findings independently verified for current reachability, the failure mechanism, existing protections, and the necessity of the proposed repair. Model agreement is not evidence. Keep confirmed defects, unresolved factual questions, rejected findings, and future suggestions distinct.
4. Assign confirmed repairs to the implementer. Do not add speculative guards, retries, fallbacks, compatibility layers, or abstractions merely to satisfy a review suggestion.
5. After the repair is implemented, push the new head, obtain CI for it, and reassess review eligibility. Revalidate previous defects and review newly changed behavior. A later exemption does not erase a confirmed unresolved defect.

Required independent discovery remains pending if the necessary agents cannot run. Agent review does not replace required human or Code Owner approval. Never bypass provider policy or approve on the user's behalf.

## Merge

Ticket or requirement approval does not confirm this merge. Once the following facts hold, present the concrete PR URL, source and target branches, head SHA, a concise change summary, CI results, review results or the recorded exemption, and any material consequences. Ask the user to confirm merging this PR and wait:

- The agreed scope for this PR is implemented and verified, its blockers are satisfied, and the PR targets the intended repository/branch.
- The worktree has no uncommitted task fixes, and the remote head is the exact head whose CI passed and whose review result or exemption was recorded.
- Expected CI checks for the current candidate passed. Either required discovery and finding verification completed or the current diff qualifies for a recorded small-feature/UI-only exemption. No known blocking defect or acceptance gap remains unresolved.
- Required provider approvals and review-thread policies are satisfied, the PR is ready and mergeable, and branch/ruleset requirements are met.

Do not merge, enqueue, or enable auto-merge while the confirmation is pending. An explicit confirmation to merge the presented PR/head satisfies this checkpoint; do not ask again for that same unchanged result. For multiple PRs, obtain approval for each concrete PR, or an explicit batch approval identifying every included PR/head.

After confirmation, re-read head/base and provider gate status immediately before merging. If the head changed, restart CI, reassess review eligibility, complete any required review, and obtain new confirmation for the changed result. If the base advanced, refresh the comparison and integration evidence; update the branch when required and recheck/reassess any resulting changes. A changed integration result or material consequence requires renewed confirmation. Do not resolve unknown or conflicting gate state optimistically.

Use the provider's expected-head compare-and-merge option where available (for GitHub CLI, inspect current `gh pr merge --help` for `--match-head-commit`). Prefer the repo's configured merge method/queue; if unspecified, choose an enabled method consistent with recent project practice. Never use an admin bypass or disable protection. If a merge queue is required, follow its candidate checks and wait for an actual merged result.

Prefer a guarded immediate merge after confirmation. Do not enable persistent auto-merge that could apply the user's approval to a future head. For a required merge queue, confirm the presented PR first, retain its approved head, and verify the queue has not substituted an unapproved head. Do not report success merely because a merge command returned without error.

Query the provider to confirm `MERGED`, the destination branch, and merge commit. Verify completed ticket status and update it when authorized and necessary; only close a parent feature after all of its in-scope acceptance criteria and child deliveries are complete. Keep any auto-triggered deployment outcome distinct from the merge outcome. Do not run separate production commands unless they are authorized by the request or established project workflow.

## Delete the merged branch

The owner authorizes automatic cleanup of the delivered PR's source branch after confirmed merge. This cleanup needs no additional confirmation beyond the PR-merge checkpoint.

1. First verify the provider reports `MERGED` and record the merged PR's source repository, source branch, and head SHA. A closed unmerged PR, queued merge, or enabled auto-merge is not sufficient. Never delete the target/default/protected branch or a shared integration branch still needed by open work.
2. Check that no other open PR uses this branch as its source or base. If it still supports another ticket or stacked PR, retain it and report the dependency.
3. Delete the exact remote source branch, using an expected-head conditional deletion so a concurrent push cannot be removed. Its current tip must still match the merged PR head; retain a branch that has advanced or whose identity is uncertain. If the provider already removed it, treat cleanup as complete. Verify the remote ref is absent afterward.
4. Inspect local branch state and `git worktree list`. If the current clean worktree is on this branch, switch it to the updated target branch, or detach at the verified merge commit when the target is checked out elsewhere. Do not disturb another worktree or an active operation, discard changes, or remove worktree directories as part of branch cleanup.
5. Delete the local source branch only when no worktree still checks it out and it contains no work beyond the verified merged PR. Prefer normal merged-branch deletion. Squash/rebase merges may fail an ancestry check: use the provider's verified merged head and the local tip to establish that no extra commits would be lost before removing that exact branch. If this cannot be established, retain it and report why. Never force-delete merely to silence a warning.
6. Prune stale tracking refs for the relevant remote and verify the local/remote results. Record cleanup in the checkpoint and final outcome. A cleanup failure is reported as "merged; branch cleanup pending" and must not trigger another merge attempt.

## Blockers and recovery

- Missing credentials, unavailable required CI/review, missing human approval, or an irreducible product decision leaves the affected gate pending. Complete independent preparation and report the exact dependency.
- A network timeout after issue/PR creation or merge may mean the mutation succeeded. Query the remote state before retrying so recovery does not duplicate artifacts or misreport a merge.
- Fix/review iterations may continue while new evidence drives progress. When the same blocker persists after diagnosis, or repair requires expanding scope, stop that dependent action with evidence and a specific next step. Do not consume repeated cycles on unchanged external state.
- A revoked merge instruction, changed scope, or explicit pause takes effect immediately. Preserve a checkpoint and do not proceed under the previous stopping point.
