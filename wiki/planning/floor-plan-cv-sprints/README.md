---
title: Floor-plan CV — sprint task breakdown
type: plan
last_verified: 2026-06-07
tags: [plan, sprints, floor-plan-cv, cv, task-list]
status: design-approved
---

# Floor-plan CV — sprint task breakdown

## For future Claude

This is a plan-folder index — the entry point for the 5-sprint execution
breakdown of the floor-plan CV project. The architectural decisions live
in the sibling [[planning/PoCs/floor-plan-cv|floor-plan-cv plan doc]];
this folder holds the per-sprint task lists. Read this README first when
picking up the project mid-flight; it routes you to the right sprint file.

Task-level decomposition of the 5 sprints sized in
[[planning/PoCs/floor-plan-cv]]. That plan doc holds the
**architectural decisions** (Q1–Q13 interview). This folder holds the
**execution breakdown** — one file per sprint, tasks numbered
T<sprint>.<n>, each with files touched + acceptance criteria +
dependencies.

## When to read this

Read this when:
- You're picking up a sprint mid-execution and need to know which tasks
  are done vs. open.
- You're estimating effort for a single task before committing to it.
- You're hand-rolling a PR scope and need to know which tasks naturally
  group into one commit.

Don't read this when:
- You need the *why* behind a design decision — go to the plan doc.
- You're picking the next sprint to start — go to the plan doc's sprint
  sizing table.

## Sprints in topological order

| Sprint | Theme | File | Depends on | Effort |
|---|---|---|---|---|
| S+1 | Surface Zome native data | [[planning/floor-plan-cv-sprints/s1-surface]] | — | ~1 week |
| S+2 | Archive plans to MinIO | [[planning/floor-plan-cv-sprints/s2-archive]] | — (parallel-safe with S+1) | ~1.5 weeks |
| S+3 | Experiments (OCR + bake-off) | [[planning/floor-plan-cv-sprints/s3-experiments]] | S+2 (needs blobs) | ~3 days |
| S+4 | CV production pipeline | [[planning/floor-plan-cv-sprints/s4-cv]] | S+3 (gated decisions) | ~1.5 weeks |
| S+5 | Migrate legacy + retire old DAG | [[planning/floor-plan-cv-sprints/s5-migration]] | S+1, S+4 | ~1 week |

**Parallelism note:** S+1 and S+2 share no files and can run concurrently
if you have two pairs of hands. S+3, S+4, S+5 are strictly sequential.

## Task numbering convention

`T<sprint>.<task>` — e.g. `T2.4` = Sprint 2 task 4.

Within a sprint file each task has:
- **What** (1-2 sentence outcome)
- **Files** (paths to create/modify)
- **Acceptance** (1-3 verifiable checks)
- **Depends on** (other task IDs)

## How to use these in a session

1. Open the relevant sprint file.
2. Pick a task that has no open dependencies.
3. Treat the **Acceptance** block as your definition of done.
4. Cross off completed tasks by adding `✓` at the start of the task heading
   (e.g. `## ✓ T2.4 — ...`) — keeps the file as a live checklist.
5. Append a one-line entry to [[log]] on commit per
   project CLAUDE.md rules.
