---
name: implement
description: "Implement an agreed behavior or approved ticket against its design, with focused local checks. Use for feature work, scoped fixes, or evidence-backed repairs."
metadata:
  collection: windflow
---

# Implement

Turn the agreed behavior and design into a scoped code change. Accept a ticket, spec, or sufficiently clear instruction; do not require Windflow or another installed skill. Resolve only material gaps in product intent.

Read repository instructions, current callers, the design revision, acceptance criteria, exclusions, and existing dirty work. Reuse relevant investigation and verification evidence.

## Establish ownership

In an orchestrated run, the worker owns the assigned code and local checks. Product decisions, integration, and Git or tracker mutations stay with the parent; the Windflow coordinator defines that split. Follow the workspace and scope the parent assigns.

When this skill is called directly, the current agent owns the requested implementation. Respect a local-only instruction and any workspace the user names.

An isolated worktree is the default for orchestrated and parallel implementation. When the user specifies a workspace, use that one. Otherwise create or reuse an isolated worktree and branch. Implement on the target or default branch only when the user assigns that workspace.

Name the branch from the repository's convention or the user's requested name. Do not hardcode a `codex/` prefix.

Preserve unrelated files and staging. If the change depends on uncommitted user edits, account for them explicitly. Do not omit, stage, stash, reset, or publish them silently. Stage only this task's changes. Run the repository's pre-commit checks before committing. Do not weaken a test or required check to make a gate pass.

For parallel work, divide independent behavior with explicit ownership and separate writable worktrees. Someone must own integration and cross-slice checks. Do not run simultaneous writers in one checkout.

## Make the change

Inspect affected callers before changing a contract. Implement the smallest change that satisfies current behavior and constraints.

For a bug, obtain a reproduction or concrete evidence of the reported failure, test the causal mechanism, repair it, and recheck the original scenario. Use a failing regression test first when an appropriate economical boundary exists. Do not create a test that cannot exercise the real bug.

If the design fails, report the violated assumption, evidence, affected behavior, and whether independent work can continue. The parent resolves technical changes and returns material product choices to the user. Do not silently revise the contract or accumulate compensating layers.

## Check and return

Run focused existing tests, affected-caller checks, type/source checks, and relevant UI/runtime observations. Do not automatically run the full local suite. Explain a concrete reason before expanding coverage, preserve required external CI, and reuse passing checks unless relevant changes or evidence gaps justify another run.

Return the baseline and design revision, changed files, acceptance evidence, commands/results, unrun checks, and unresolved deviations. The coordinator can use this receipt for acceptance without repeating successful checks.

Stop at the requested implementation outcome. Commits, publication, review, or merge require the corresponding authorization; do not start a delivery workflow merely because code is complete.

Sources and revisions: [THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES.md), [upstream-lock.json](../../upstream-lock.json).
