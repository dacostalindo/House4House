# House4House — Claude Code project rules

This file is the entry point for Claude Code sessions on House4House. Project-specific stack, conventions, and area rules will be filled in as Phase 3 of the dev-tooling design lands (`pipelines/CLAUDE.md`, `dbt/CLAUDE.md`, `apps/CLAUDE.md`). Until then, the routing section below is the only authoritative rule.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
