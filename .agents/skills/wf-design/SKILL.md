---
name: wf-design
description: "Have independent agents propose approaches to an agreed problem, then settle one into interfaces, data shapes, ownership, and a verification plan. Use before implementation when the structure or interfaces are undecided."
metadata:
  collection: windflow
---

# Design

Get independent alternatives first, then converge on one. The output is a design contract, not production code or published tickets.

Start from the confirmed requirement and the evidence. If a product decision is still open (what users see or can do, what data is kept, compatibility, or scope), take it back to the user before designing around it.

## Compare independent approaches

Usually ask two candidate agents for complete proposals, each with the same brief, and keep them from seeing each other's work. Independence is the point: two proposals that saw each other are one proposal.

```text
Propose a design for queuing offline edits and marking conflicts. Work alone; write only to the output path.
Requirement: issue #301 (acceptance criteria 1-4)
Evidence: server dedupes on Idempotency-Key (server/docs.go:88); drafts persist in IndexedDB (store/draft.ts).
Constraint: no server schema change in this ticket.
Output: <scratch path outside the repository>/candidate-a.md
Return: caller usage, data shapes and states, conflict handling, tradeoffs, assumptions,
  and the cheapest check that would settle each uncertain claim.
```

Pick criteria that matter for this task, choose a base, and borrow compatible improvements from the other proposal. If the proposals disagree because product intent is missing, ask the user rather than splitting the difference. If you could not run independent candidates, say the comparison was limited.

## Converge in the owner

The agent that understands the requirements writes the final design itself, not a new architecture agent. Cover what implementation needs: caller usage and interfaces, data shapes and state ownership, error handling, module boundaries, compatibility or migration, what to verify, and why this approach won. Keep it proportional to the change. Do not add layers or abstractions without a current need.

Reuse an approved design while it still applies; reopen it only when new evidence breaks it. When implementation contradicts the contract, the owner adjusts the technical details and takes product changes to the user.

Adapted from pstack `arena` and `architect` by Lauren Tan (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
