---
name: wf-investigate
description: "Trace how current code behaves and find the recorded reasons behind it in commits, PRs, issues, and ADRs. Use for subsystem questions, regression causes, or facts needed before a design."
metadata:
  collection: windflow
---

# Investigate

Explain how the code behaves now and why, with evidence. This skill stands alone; it does not start an interview, implementation, or delivery.

Trace the behavior through the code: entrypoints, callers, data flow, who owns which state, failure paths, and the protections already in place. Then find out why the relevant constraints exist, using whatever history is available: blame and log, the PRs and issues behind commits, ADRs, incident records. Note the commit you read.

Separate what is documented, what you observed, what you infer, and what is still unknown. Missing history is an unknown, not room to invent a rationale. Say whether an old constraint still applies.

Split a large question among several investigators if that helps. When a coordinating agent dispatched you, report to it. Product choices stay with the user.

```text
Question: Why does save retry at most 3 times?
Read at: main@a1b2c3d
Behavior: SaveButton.onClick -> api/save.ts saveDoc -> retry.ts withRetry(max=3) -> POST /docs/:id.
  The server dedupes on Idempotency-Key (server/docs.go:88).
State: the client owns pendingSave (store/doc.ts); the server owns the document version.
Documented: PR #212 capped retries after duplicate writes on flaky networks (links the incident).
Inferred: retries are safe only while the key is reused; withRetry reuses it (retry.ts:41).
Unknown: whether mobile clients send the key; their source is not in this repository.
```

Adapted from pstack `how` and `why` by Lauren Tan (MIT). Sources, revisions, and license notices: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
