---
name: investigate
description: "Explain current code behavior and the recorded reasons behind it. Use for subsystem questions, regression investigation, or gathering facts before design."
metadata:
  collection: windflow
---

# Investigate

Combine source tracing and historical investigation into one evidence-backed explanation. This skill runs on its own; it does not start a requirements interview, implementation, or delivery.

## Establish the question

Read applicable repository guidance and pin the relevant revision or working-tree snapshot. Identify the behavior or decision being investigated. When the target is vague, state a bounded interpretation and explore it.

Trace current entrypoints, callers, data flow, state ownership, failures, and existing protections. Read the relevant tests and observations. A list of filenames is not a behavioral explanation.

Then investigate why the relevant constraints exist: blame/history, substantive commits and PR discussions, issues, ADRs, and available incident or runtime records. Choose sources relevant to the question. Missing historical evidence is an unknown, not permission to invent a rationale. Check whether an old constraint still applies.

## Use agents where they help

In a Windflow run, investigation workers return evidence to the parent before it interviews the user. For direct invocation, the current agent owns the explanation and may investigate locally or delegate bounded questions.

Partition a large investigation by distinct questions and keep source reads on a stable baseline. Give each investigator the target, revision, known entrypoints, and required evidence. Source reads do not authorize external messages or repository writes.

New questions return through the parent. Reuse a knowledgeable investigator when useful; keep its sources accessible so another worker can continue without relying only on a summary.

## Return usable context

Distinguish documented facts, observed behavior, inferences, competing explanations, and unknowns. Include:
- The actual behavior chain and who owns each important state.
- Source paths/symbols with revisions and linked historical records.
- Constraints that must be preserved and the reasons behind them.
- Commands or observations, with their scope and limitations.
- Unanswered facts that affect the next decision.

For greenfield work, investigate requirements, dependencies, and platform constraints, and state that repository history is absent. Stop with the requested explanation or evidence packet; product choices remain the user's.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
