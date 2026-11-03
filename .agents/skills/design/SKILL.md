---
name: design
description: "Compare independent approaches to an agreed problem, then converge the chosen approach into interfaces, types, ownership, and a verification plan. Use when choosing a structure or settling interfaces before implementation."
metadata:
  collection: windflow
---

# Design

One skill owns the complete design decision: independent alternatives first, architectural convergence second. Its output is a design contract, not production implementation or published tickets.

Read the confirmed requirement, acceptance criteria, investigation evidence, constraints, and unknowns. If a material product decision is unresolved, return that decision to the user or coordinating parent. Obtain missing technical facts through bounded investigation without requiring another installed skill.

## Compare independent approaches

The owner freezes the current context revision and chooses concrete comparison criteria for this task: behavior coverage, compatibility, simplicity, caller burden, testability, or measured cost as relevant.

Normally ask two independent candidate agents for coherent solutions to the same problem. Give each the same confirmed facts, source evidence, constraints, and writable output location. Candidates may inspect original sources and ask the owner for missing facts. They do not inspect each other's unfinished proposals or change production files.

Require representative caller usage, assumptions, tradeoffs, and ways to test uncertain claims. The owner reads every result, selects a base against the criteria, and combines only compatible, justified improvements. A disagreement that exposes missing product intent returns to the user; do not average incompatible requirements.

Use native agent capacity and configured models. Do not require a fixed model family. If independent candidates cannot run, disclose the limited comparison and distinguish it from independent exploration.

## Converge in the owner

The same owner that understands the requirements develops the selected proposal. In a Windflow run this is the parent, not a new architecture agent.

Write:
- Representative caller usage and interfaces.
- Data shapes, legal states, transitions, and state ownership.
- Error responsibilities and existing protections to preserve.
- Module boundaries, compatibility or migration requirements.
- Observable behavior to verify and the relevant test boundaries.
- Reasons for the chosen approach, rejected alternatives, and remaining assumptions.

Keep the structure proportional to the agreed behavior. Do not add fallback layers, compatibility wrappers, or abstractions without a current need. A narrow specialist may resolve a local question; overall design ownership stays with the parent.

Do not automatically start a second competition during convergence. Reuse an approved applicable design for its tickets or a fully specified mechanical edit. Reopen a decision only when new evidence invalidates it.

## Handoff

Return the design revision, contracts, evidence links, accepted tradeoffs, and unresolved facts. If implementation later contradicts the contract, the owner evaluates the evidence, updates technical choices within scope, and sends material product changes back to the user.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
