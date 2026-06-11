---
title: Agentic pipeline — sprint task breakdown
type: plan
last_verified: 2026-06-11
tags: [plan, sprints, agentic, llm, task-list]
status: not-yet-decomposed
---

# Agentic pipeline — sprint task breakdown

## For future Claude

This is the sprint-breakdown folder for the agentic-pipeline PoC. **No
per-sprint files have been authored yet** — H4H absorption of the PoC is
still pending product decision (see status in
[[planning/PoCs/agentic-pipeline/design]]). When sprint planning happens,
the per-sprint files should land here following the
[[planning/PoCs/floor-plan-cv/sprints/README|floor-plan-cv sprints README]]
pattern: one file per sprint, tasks numbered `T<sprint>.<n>`, each with
files touched + acceptance criteria + dependencies.

## Status

PoC validated outside H4H on 2026-05-15 in
`~/Desktop/Apps/Knowledge-graph-PoC/agentic-pipeline/` (21 ok rows over 20
H4H-sourced development names, 100% precision on verified ground truth).
Per [[UC-4]], the integration work is currently absorbed into UC-4's
sprint plan rather than this folder — UC-4 owns the actor-graph use case
that the agentic pipeline feeds. This folder exists for structural
consistency with [[planning/PoCs/floor-plan-cv/design]] and as the natural home
if/when standalone agentic-pipeline sprints emerge outside UC-4 scope.

## When sprint files do land here

Mirror the shape of
[[planning/PoCs/floor-plan-cv/sprints/README|floor-plan-cv sprints README]]:
one file per sprint (`s1-<theme>.md`, `s2-<theme>.md`, …), `T<sprint>.<n>`
task numbering, and a topologically-ordered sprint table in this README.
Architectural decisions stay in
[[planning/PoCs/agentic-pipeline/design]]; this folder holds execution
breakdown only.
