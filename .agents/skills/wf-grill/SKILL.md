---
name: wf-grill
description: "Clarify a product requirement or design decision through an informed interview. Use when behavior, acceptance criteria, or scope remain unsettled."
metadata:
  collection: windflow
---

# Grill

Work with the user until the behavior, acceptance criteria, scope, and important tradeoffs are clear. Finishing the interview does not authorize implementation or publication.

Ground yourself first: read whatever investigation exists and check the code for facts. Ask the user only product decisions, meaning choices that change what users see or can do, what data is kept, compatibility, cost, or scope. Decide technical details yourself unless the user wants to. Facts you can find in the code or with a quick experiment are yours to find, not the user's to guess.

Work through the decisions as a tree. Each round, ask the questions whose prerequisites are settled, and give a recommended answer with its reason. Hold dependent questions for a later round. Cover what this request needs, not every future feature.

```text
Settled: offline edits are queued locally; sync runs on reconnect.

1. Two devices edit the same paragraph offline. Which version wins?
   a) Last write wins  b) Keep both and mark a conflict  c) Block offline editing
   Recommend b: silently overwriting loses user text.
2. Should queued edits survive an app restart?
   Recommend yes: drafts already persist in IndexedDB (store/draft.ts).

Next round, after 1: how a conflict is shown.
Checking in code, not asking: whether the server tracks per-paragraph versions.
```

To finish, present the agreed behavior, acceptance criteria, exclusions, and open questions, and get the user's agreement before dependent work starts. An agreement the user already gave for the same scope counts.

Adapted from Matt Pocock's `grilling` (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
