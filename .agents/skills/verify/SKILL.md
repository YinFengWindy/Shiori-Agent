---
name: verify
description: "Assess whether an existing change meets agreed acceptance criteria using actual artifacts and focused evidence. Use for acceptance checks without implementing changes."
metadata:
  collection: windflow
---

# Verify

Acceptance is not review, and a pass is not merge approval. The Windflow coordinator defines that split. This stage only judges whether an existing change meets the agreed acceptance criteria. It does not implement fixes or search for unrelated defects.

Read the agreed acceptance criteria, current design, repository instructions, exact code or build version, and available results. If acceptance criteria are missing, derive a proposed check from the clear request or resolve a material ambiguity with the user. Do not invent new requirements.

## Map evidence to behavior

For each criterion, identify what observation would establish it and what existing evidence already covers it. Verify that prior results belong to the relevant code and environment.

Distinguish static checks, unit behavior, integration behavior, and real UI, provider, or hardware behavior. A passing compilation or an implementer's success statement alone is not complete acceptance evidence.

Inspect the actual artifact and affected callers. Run only the focused checks or runtime observations needed to fill evidence gaps. Reuse applicable passing results. Do not automatically run a full local suite or replace required external CI with a narrower local result.

## Report the result

Mark each criterion met, unmet, or unverified, with evidence, its version/environment, and any limitations. A failed check is not an unverified pass; an unavailable environment is not a confirmed defect.

Give reproducible steps or concrete evidence for failures. Return implementation problems to the coordinating parent or user; do not fix them unless requested. Material product changes return to the user.

Return an acceptance receipt with the artifact version, criteria, commands and results, gaps, and what would resolve them.
