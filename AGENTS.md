# Maintaining dev_co

This repository is the source for the shared Codex / Claude Code skill.

- Keep the skill name `dev_co`. The underscore is intentional and supported by the tested hosts.
- Keep `SKILL.md` compact. Put conditional detail in `references/`, with clear reading conditions; standalone evaluations and isolated edits must not become default development workflows.
- Keep runtime helpers dependency-free on Python 3.10+ for macOS/Linux. Use the existing standard-library test suite: `python3 -m unittest discover -s tests -v`.
- Preserve evidence invalidation, process cleanup, and project-path boundaries. A passing gate must never grant permissions or imply deployment/user acceptance.
- Installation must preserve existing user files and must not enable hooks or replace global instructions automatically.
- Keep README installation and routing guidance consistent with `SKILL.md`. Do not commit generated evidence, local conversations, credentials, or machine-specific configuration.
