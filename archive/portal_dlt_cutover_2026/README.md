# Portal dlt Cutover 2026 — Archive

Historical artifacts from the dlt-based bronze cutover for the three real-estate portals (RE/MAX, Idealista, Zome).

**Path references inside these files reflect the pre-rename `pipelines/api/{portal}/` layout — do not update.** They are kept here as-is for incident archaeology and rollback reference only.

The portals now live at `pipelines/portals/{remax,idealista,zome}/`. Any new CUTOVER docs (if needed for future migrations) should be written there, not here.

| File | Source pre-rename path | Purpose |
|---|---|---|
| `remax/CUTOVER.md` | `pipelines/api/remax/CUTOVER.md` | RE/MAX dlt cutover plan + execution log |
| `remax/rollback_remax.sql` | `pipelines/api/remax/rollback_remax.sql` | RE/MAX bronze table rollback DDL |
| `idealista/CUTOVER.md` | `pipelines/api/idealista/CUTOVER.md` | Idealista dlt cutover plan |
| `idealista/rollback_idealista.sql` | `pipelines/api/idealista/rollback_idealista.sql` | Idealista bronze rollback DDL |
| `zome/CUTOVER.md` | `pipelines/api/zome/CUTOVER.md` | Zome dlt cutover plan |
| `zome/rollback_zome.sql` | `pipelines/api/zome/rollback_zome.sql` | Zome bronze rollback DDL |

## When to consult these

- **Rollback** — if a portal's dlt pipeline misbehaves and needs reverting to the pre-dlt schema, the corresponding `rollback_{portal}.sql` reverses the bronze tables. Beware: paths in those scripts are pre-rename.
- **Incident archaeology** — to understand what was migrated, when, and why.
- **Pattern reference** — when planning future schema cutovers, these documents the validation gates, dual-write strategies, and shadow-run patterns used.

## Archive convention

This directory establishes `archive/` at repo root as the canonical location for **retired-but-kept-for-history** files: completed migrations, deprecated configs, sunset implementations. New retirements should follow the pattern `archive/{topic}_{year}/`.

**Date archived:** 2026-04-29
**Reason:** Sprint 4.4 Workstream A — folder rename `pipelines/api/{remax,idealista,zome}` → `pipelines/portals/`. See `docs/adr/001-pipelines-portals-namespace.md` (forthcoming in Workstream E).
