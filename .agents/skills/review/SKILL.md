---
name: review
description: "Find defects in a fixed change, independently verify their causal mechanisms, and assess whether proposed repairs are necessary. Use for code or PR review without automatic fixes."
metadata:
  collection: windflow
---

# Review

Review is not acceptance. The Windflow coordinator defines that split. Read the [review method](references/method.md) and apply it to the fixed change: find reachable defects, verify their mechanisms, and judge whether a proposed repair is necessary. An acceptance receipt is not this review.

This package contains the complete method and can review a diff or PR without installing Windflow.

Accept a comparison base or PR, the requested scope, available requirements and constraints, and relevant acceptance results. Resolve or state the comparison baseline before discovery. Missing a written spec does not prevent reviewing behavior that is clear from the request and code; report genuine limits.

Use an independent finder and a separate verification task for its findings. Scale coverage to current impact, not a fixed reviewer count. The method distinguishes confirmed defects, unresolved questions, rejected findings, and future suggestions.

In a Windflow run, return results to the parent for authorized repairs. When invoked directly for review, stop at findings and repair directions. Do not modify implementation, publish comments, or merge unless the user requests those actions.

Whether a delivery needs automatic review is the caller's decision. An explicit review request runs regardless of a broader workflow's exemptions.
