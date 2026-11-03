# Execution records

Short records that mark which requirement is final, let work resume, and back up claims of completion. They add no authorization and replace no confirmation. Use them when they help, for multi-ticket work, resuming, or handing off to another agent; a single-ticket change can just report its status in a few lines:

```text
Ticket: #302 queue offline edits (spec #301)
State: implemented and accepted; PR #310 CI green; review found no defects
Next: waiting for your confirmation to merge PR #310 at 9f8e7d6
```

## SPEC READY

Once the requirement is agreed and the spec is published or chosen, mark it so later drafts can't be mistaken for the final one. Include the spec link, the agreed outcome, non-goals, how it will be verified, the overlap decision, and which approvals are on record. `SPEC READY` means settled, not approved for implementation or merge. If a product decision is still missing, write `SPEC NOT READY` and name it. If the user hands you an approved spec in some other form, accept it as it is.

## Execution contract (optional)

Write one only when handing work to another agent or session, or when the context needs a durable checkpoint. It describes one ticket:
- what is already done, with evidence;
- what remains, as observable conditions;
- the current branch and head, and any uncommitted work to preserve;
- the checks to run;
- scope exclusions;
- the authorizations already on record.

Check each criterion against the code, not against labels or earlier claims. A contract carries existing authorizations forward and grants no new ones. Merge still needs its own confirmation. A contract is a document, not a reason to start a new session or fork.

## Receipt

When handing off, asking for merge confirmation, or finishing, report the following, and use the receipt as the normal reply rather than a separate artifact:
- the state: `ready-for-merge`, `merged`, `partial`, or `blocked`;
- the branch, head, and PR;
- each acceptance criterion as met, unmet, or unverified, with its evidence;
- the checks tied to that head;
- the review result;
- the approvals on record;
- what is left.

Name the checks you did not run, and remember that a pending confirmation means `ready-for-merge`, not merged.

Adapted from readiness markers and evidence receipts in tt-a1i/matt-skills-with-to-goal. Sources and revisions: [THIRD_PARTY_NOTICES](https://github.com/YinFengWindy/windflow/blob/main/THIRD_PARTY_NOTICES.md).
