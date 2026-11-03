---
name: plan
description: "Turn agreed requirements and a design into a specification and verifiable tickets. Use for drafting specs, proposing task breakdowns, or publishing approved plans."
metadata:
  collection: windflow
---

# Plan

Produce a specification, ticket breakdown, or both, according to the request. Read the agreed requirement, design, evidence, existing tracker artifacts, and repository guidance. These can come directly from the user; no other skill installation is required.

## Write the spec

Record the user problem, intended behavior, observable acceptance criteria, exclusions, constraints, material design decisions and reasons, and verification approach. Link source evidence rather than copying whole investigation reports. Scale the document to the work.

Technical testing choices are delegated to the agent. Missing material product decisions must remain explicit; obtain the user's decision before claiming the spec is ready.

## Check overlap before publication

For a new delivery spec, draft it first, then search open and closed issues in the resolved target repository using behavior, domain synonyms, and affected components. Read plausible candidates and relevant comments. Do this once per scope; retain the result for downstream tickets.

If overlap is plausible, show the candidate URLs, shared behavior, differences, and your recommendation. Wait for the user's choice to reuse, extend, create separately, or drop before publishing. Incomplete search access is not proof of no duplicates.

A supplied existing implementation issue already identifies the chosen scope. Local draft-only requests do not require remote access or issue publication. After an uncertain create timeout, reconcile that operation instead of creating again.

## Propose independently verifiable work

Each ticket identifies delivered behavior, acceptance criteria, the current spec/design revision, exclusions, and real blockers. Prefer end-to-end capabilities over layers that cannot be accepted alone.

For a broad migration, choose expand/migrate/contract steps when compatibility requires them. Use an integration branch when intermediate steps genuinely cannot land green separately. Do not keep compatibility layers without a current consumer.

Show the proposed breakdown and wait for approval before publishing tickets or starting their implementation. Reuse unchanged approval. Material changes to scope, granularity, or dependencies require renewed agreement. Implementing one selected existing ticket does not require inventing a new split.

## Publish only within the request

For authorized full delivery, publish the parent spec after the overlap decision, then publish approved tickets in dependency order. A small change can use one issue as both spec and executable ticket; publish it after applicable ticket approval and before implementation. Clear requirements remove repeated interviewing, not the delivery issue step.

Use the tracker's existing labels and native sub-issue/blocking links where available. Preserve the parent spec and returned identifiers. A blocker is satisfied only when the required behavior exists, not merely because its issue was closed.

Return the spec, breakdown, dependencies, publication state, overlap decision, and recorded approvals. Stop there; a planning request does not authorize implementation or merge.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
