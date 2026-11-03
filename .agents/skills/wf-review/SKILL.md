---
name: wf-review
description: "Find defects in a pinned code change or PR, independently verify each finding's failure mechanism, and judge whether proposed repairs are needed. Use for code or PR review; reports findings without changing code."
metadata:
  collection: windflow
---

# Review

Review asks where the current change can still fail. Acceptance (the separate wf-verify skill) asks whether the agreed behavior works; an acceptance pass is not a review.

Pin the change first: an exact base and head, or a saved snapshot of uncommitted work. Then follow the [review method](references/method.md): independent discovery, separate verification of each finding, and a check on whether each proposed repair is actually needed. No other skill is required.

Use whatever requirements and acceptance results exist. A missing spec does not block reviewing behavior that is clear from the request and the code.

Report findings and repair directions; do not change the implementation, post comments, or merge unless the user asks. When a coordinating agent assigned the review, report to it.
