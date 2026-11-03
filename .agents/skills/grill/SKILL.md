---
name: grill
description: "Clarify a product requirement or design decision through an informed interview. Use when behavior, acceptance criteria, or scope remain unsettled."
metadata:
  collection: windflow
---

# Grill

Work with the user until the requested behavior, acceptance criteria, scope, and important tradeoffs are understood. Do not implement or publish simply because the interview is complete.

## Ground the interview

Read the supplied investigation and decisions first. Check relevant project facts before asking product questions. If no investigation packet exists, inspect the available sources or dispatch bounded factual questions yourself; this skill does not require another installed skill.

In a Windflow run, the parent conducts the interview. Investigators answer factual questions; they do not choose product behavior.

## Work the decision tree

Map decisions and their prerequisites. Ask a round of independent questions whose prerequisites are settled. Recommend an answer to each with its reason. Questions that depend on an unanswered decision wait for a later round.

Use concise numbered questions and plain choices. After the user answers, update settled decisions and recompute the next round. Do not repeatedly ask for information already confirmed.

Facts are the agent's responsibility. If a decision depends on a new factual question, investigate it and keep the dependent question pending. Continue independent questions while that investigation runs. Do not ask the user to guess behavior that can be observed in the code or a bounded experiment.

Cover decisions necessary for this request, not every possible future feature. Separate a product choice from an implementation detail the user has delegated.

## Confirm the result

Present the intended behavior, observable acceptance criteria, scope exclusions, and material tradeoffs, with unresolved matters explicit. Obtain agreement before dependent work. Existing explicit agreement for the same scope satisfies this checkpoint.

Return the confirmed requirement and its reasons, referenced evidence, unresolved questions, and next requested stage. Keep technical testing choices with the agent unless they change a material product decision.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
