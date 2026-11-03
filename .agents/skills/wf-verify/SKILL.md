---
name: wf-verify
description: "Check an existing change against its agreed acceptance criteria and report each criterion as met, unmet, or unverified, with evidence. Use for acceptance checks; does not hunt for unrelated defects or fix anything."
metadata:
  collection: windflow
---

# Verify

Acceptance asks whether the agreed behavior works. Review (the separate wf-review skill) asks where the change can still fail. A pass here is neither a review nor merge approval.

For each acceptance criterion, decide what observation would prove it, reuse existing results that belong to this exact version, and fill only the gaps. A compile, a green unit test, or the implementer's word may not reach the behavior the criterion describes; say which level the evidence reaches. If there are no criteria, propose checks from the request rather than inventing requirements.

Report failures with steps to reproduce, and send them back to whoever owns the change instead of fixing them.

```text
Artifact: feat/offline-queue @ 9f8e7d6, local dev server
1. Offline edit survives reload: met. Reloaded with the network off; the edit was present.
2. Queued edits are sent once, in order: met. queue.test.ts passes at 9f8e7d6; server log shows 3 POSTs with distinct keys.
3. Conflict is marked when two devices edit: unverified. No second device available; resolve with two browser profiles against staging.
Failures: none
```

A failed check is unmet, not unverified; an environment you could not reach is unverified, not a defect.
