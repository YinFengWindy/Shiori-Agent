# Execution Context

Use these compact records to distinguish the final requirement from earlier drafts, resume partial work, and substantiate completion. They adapt readiness markers and optional evidence-bearing handoffs. Sources and revisions: [THIRD_PARTY_NOTICES](../../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../../upstream-lock.json). They do not add authorization, require a new task, or replace the existing confirmation gates.

## Identify the final spec

After requirement agreement, the single similar-issue check, and spec publication or selection, include this index in the stage result. For local-only planning, reference the local spec instead. A later user correction overrides the index.

```text
SPEC READY
Source: <spec URL/path and revision or last known update>
Outcome: <agreed behavior>
Context and design: <current revision; investigation evidence; selected proposal; design contract>
Repository and baseline: <repository, branch, commit>
Verification: <observable behavior and repo-mandated checks>
Non-goals: <explicit scope exclusions>
Similar issues: <recorded outcome and user decision, if any>
Approvals: <requirement agreed; breakdown pending/approved>
Next action: <propose tickets / resume approved ticket>
```

`SPEC READY` means the requirement is settled, not that implementation or merge has been approved. Do not mark contradictory or materially incomplete requirements ready. Name the missing decision as `SPEC NOT READY`. Reuse an explicitly approved source supplied by the user without requiring them to reproduce this exact format. Technical verification choices remain the agent's responsibility.

## Optional execution contract

Compile a contract only when asked for a handoff/goal, when transferring work to an explicitly requested new task, or when essential context needs a durable checkpoint. Do not re-interview the user about settled decisions or duplicate the complete spec. Ordinary small changes continue in the current task without this artifact.

Read the source ticket, spec, relevant comments, and actual repository state. Select one unblocked ticket within the approved scope; use the user's selected ticket or the established dependency order. Check each acceptance criterion against available evidence and classify it as evidenced complete, incomplete, or unverified. A label, commit message, or earlier claim is not verification. If a required source or decision is missing, identify that gap rather than manufacturing an executable contract.

```text
EXECUTION CONTRACT
Outcome and selected ticket: <one independently verifiable slice>
Sources: <spec, ticket, decisions, repo guidance>
Context and design: <current revision and evidence links; rejected directions and unknowns>
Current state: <worktree, branch, HEAD, dirty files to preserve>
Evidenced complete: <criteria and evidence>
Remaining: <one observable completion condition per item>
Order: <remaining steps, preserving blockers>
Verification: <discovered commands and required CI>
Review: <required or current exemption, with reason; reassess final diff>
Scope exclusions: <what this ticket must not absorb>
Authority: <existing authorization and its source; do not widen it>
Checkpoints: <split approval; overlap decision; merge approval still pending>
Next action: <concrete first action>
```

Carry forward authorized commits, pushes, and issue/PR actions when established by the current workflow. Do not reset them to an invented blanket denial, or treat a contract as new permission. Merge still waits for confirmation of the finished PR/head. Completed work is evidence to retain, not a to-do list to repeat. Failed or unrun checks remain explicit.

Do not call a goal, scheduling, task-creation, fork, or messaging tool merely because a document is called a contract. Use new-task/fork tools only when the user explicitly asks for that action. A fork shares files unless an isolated worktree is chosen; it is not filesystem isolation. Do not automatically archive a user's task. No separate messenger or goal-crafter skill is required.

## Evidence receipt

At a meaningful handoff, before merge confirmation, or when completing delivery, give a compact evidence-bearing result. Reuse it as the normal status/final response; do not duplicate the same report under several headings or create extra tracker comments/files just for ceremony.

```text
EXECUTION RECEIPT
State: <ready-for-merge / merged / partial / blocked>
Context and design revision: <verified current contract>
Source and revision: <spec/ticket>
Branch, head, base, PR: <verified identifiers>
Acceptance: <each criterion: met/unmet/unverified + evidence>
Checks: <commands and CI results tied to the head; unrun checks named>
Review: <findings/resolution or skipped exemption and reason>
Approvals: <actual recorded confirmations; pending merge question>
External actions: <only verified issue/PR/push/merge outcomes>
Workspace and cleanup: <dirty work preserved; branch deletion done/pending>
Remaining: <gaps, blockers, or exact next user decision>
```

Keep the detail proportional to the change. Passing checks alone is not proof that every acceptance criterion is met. A pending user confirmation is `ready-for-merge`, not a merged delivery. Report work as partial when criteria or verification are incomplete. Do not turn review exemption into a passed review, invent executed commands, or expose credentials in the receipt.
