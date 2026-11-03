---
name: windflow
description: "Coordinate investigation, requirements, design, implementation, acceptance, review, and delivery using the Windflow collection. Use for a complete development workflow or resuming one."
metadata:
  collection: windflow
---

# Windflow

An optional coordinator for the Windflow skill collection. Use individual skills directly for investigation, design, writing, implementation, acceptance, review, or delivery. This entrypoint owns stage selection, continuing context, user decisions, and handoffs rather than duplicating each method.

## Load the stage you need

The stage skills are separate installable packages. This file does not contain them. Install the collection for the full workflow, or install the required subset for the requested stages.

| Stage | Skill | Owner in this workflow |
| --- | --- | --- |
| Current behavior and history | investigate | Investigation agents |
| Requirement interview | grill | Parent |
| Alternatives then architecture | design | Independent candidates, then parent convergence |
| Spec and tickets | plan | Parent |
| Code changes and local checks | implement | Implementation agent |
| Acceptance of promised behavior | verify | Parent owns the verdict |
| Defect discovery and verification | review | Independent finder and separate verification |
| PR, CI, merge, cleanup | ship | Parent |
| Clear replies and documents | write | Every author |

Locate an entry through the host's installed-skill catalog or the collection's sibling directories. Check that its frontmatter identifies collection `windflow` before using a same-named skill from another source. Read the actual SKILL.md, and pass its path and instructions to assigned workers. A name is not a tool invocation.

Hosts discover skills by name and description. This file does not declare installer dependencies. If a required stage is not installed, report the missing skill and stop that dependent stage; continue independent preparation. Do not substitute an unrelated global implementation or pretend the method ran. A subset installation need not contain skills for stages outside the user's request.

## Route intent

State the entry and the stopping point. Read [coordination](references/coordination.md) before delegation and [execution context](references/execution.md) when handing off or resuming. Use write for replies and documents. It is not an extra stage or approval.

| Request | Route | Stop |
| --- | --- | --- |
| Unsettled behavior | investigate, then grill, then design, then plan | The user has agreed the behavior, and has approved the ticket breakdown, before publication or implementation |
| Approved ticket | implement in the assigned workspace, then verify | The ticket's behavior is accepted, or an earlier stopping point the user set |
| Known defect | investigate the mechanism, then implement inside that scope | The requested fix, without opening a new feature split |
| Mechanical edit with the behavior already specified | implement | The edit itself |
| Review only | review the fixed change | Findings and repair directions |
| Deliver work that already exists | ship | The requested gate: PR, CI, review evidence, or an authorized merge |

When ship requires review, dispatch it on the fixed change and verify findings before repairs. Merge waits until the user confirms the presented PR. After that confirmation, verify the merge and any eligible source-branch cleanup.

Reuse an explicit requirement agreement, an approved design, a selected ticket, and an unchanged approval while they still apply. A selected existing ticket does not need a new breakdown. A fully specified mechanical edit does not need an interview or a design competition. Discussion, planning, local edits, review-only work, and standalone delivery stop at the requested result.

## Preserve decisions and authorization

Acceptance versus review, silence or green CI versus approval, and parent ownership of product decisions are defined in [coordination](references/coordination.md). Apply that reference at every stage.

The owner confirms requirements, the exact ticket breakdown, and the finished PR before merge. The plan skill also returns plausible issue overlap to the user. An authorization the user already gave, and any narrower stopping point, stays in force.

Use focused local checks for affected behavior and callers. Keep required external CI. Repeat a passed check only when the code changed or the evidence has a gap. Keep merged, merge-ready, partial, and unverified outcomes distinct.

## Resume

Read current repository and tracker state, the latest context and design revision, completed evidence, approvals, and the next unsatisfied gate. A changed head needs current CI and a fresh review-eligibility check. Preserve results that still apply.

This skill operates in the current task. It does not create a scheduler, new user-visible chats, or external messages unless the user asked for that action.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
