---
name: windflow
description: "Coordinate investigation, requirements, design, implementation, acceptance, review, and delivery using the Windflow collection. Use for a complete development workflow or resuming one."
metadata:
  collection: windflow
---

# Windflow

An optional coordinator for the Windflow skills. It picks the stages, carries context and decisions between them, and talks with the user; each stage's method lives in its own skill.

| Stage | Skill | Who does it |
| --- | --- | --- |
| Current behavior and history | wf-investigate | Investigation agents |
| Requirement interview | wf-grill | You (the coordinator) |
| Alternatives, then architecture | wf-design | Independent candidates, then you |
| Spec and tickets | wf-plan | You |
| Code changes and local checks | wf-implement | Implementation agents |
| Acceptance | wf-verify | You own the verdict |
| Defect discovery and verification | wf-review | An independent finder, plus separate verification |
| PR, CI, merge, cleanup | wf-ship | You |
| Replies and documents | wf-write | Whoever is writing |

Read each stage's SKILL.md and give its path to the workers you assign. If a stage skill is not installed, say so and stop that stage, rather than improvising its method. If several skills share a name, use the one whose frontmatter says `collection: windflow`.

## Route the request

State where you are starting and where you will stop. Read [coordination](references/coordination.md) before delegating, and [execution records](references/execution.md) when handing off or resuming.

| Request | Route | Stop |
| --- | --- | --- |
| Unsettled behavior | investigate, grill, design, plan | Behavior agreed and breakdown approved, before publishing or implementing |
| Approved ticket | implement, then verify | Behavior accepted, or an earlier stop the user set |
| Known defect | investigate the mechanism, then implement | The fix, with no new feature split |
| Behavior already fully specified | implement | The edit |
| Review only | review the pinned change | Findings and repair directions |
| Existing work to deliver | ship | The gate the user asked for |

Skip what is already settled: an agreed requirement, an approved design, a selected ticket, or an unchanged approval carries forward. A fully specified edit needs neither an interview nor a design competition.

## Decisions and approvals

The user confirms three things: the requirements, the ticket breakdown (for a single ticket, together with the requirements), and merging the finished PR. Nothing else stands in for those confirmations, and an authorization the user already gave stays in force. Keep merged, ready-to-merge, partial, and unverified outcomes distinct when you report.

To resume, read the current repository, tracker, and PR state, the latest decisions and evidence, and find the next unmet gate. A new head needs fresh CI and a review of what changed.

Work in the current conversation; start new sessions, scheduled jobs, or external messages only when the user asks.

Agent coordination is adapted from pstack `swarm` by Lauren Tan (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
