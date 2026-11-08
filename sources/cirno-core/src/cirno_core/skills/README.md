# Cirno Skills

Runtime discovery, metadata validation and version history live in this directory's Python modules. Bundled Markdown Skills and their resources live in `builtin/`. Home Skills belong in `<Home>/skills/<name>/SKILL.md`; history belongs in `<Home>/skills-history/`. Skills are not discovered from project workspaces.

A Skill has YAML frontmatter with `name` and `description`, followed by Markdown instructions. Optional metadata declares platform, dependency or installation requirements. Keep bundled instructions in English and use the namespaced tools in the current catalog.

| Skill | Purpose |
| --- | --- |
| `cirno-document` | Read this installation's Cirno guides |
| `memory` | Recall, checkpoints, evidence and revisions |
| `my` | Inspect and adjust permitted runtime state |
| `cron` | Scheduled reminders and recurring work |
| `skill-creator` | Create, validate and package Skills |
| `clawhub` | Find and install registry Skills into Home |
| `github` | Use the GitHub CLI |
| `summarize` | Use an installed summarization CLI |
| `tmux` | Control an interactive terminal when required |
| `weather` | Query weather services |

Use `files__search` to narrow large documentation or logs before reading full files. `output_mode="files_with_matches"` or `"count"`, filename globs and `head_limit`/`offset` keep searches bounded. Native tool names use double underscores; PTC uses dotted names.

The `cirno-document` Skill reads root `documents/` in a source checkout. Wheels embed those same guides under `cirno/skills/builtin/cirno-document/references/`; source distributions retain `documents/` for rebuilding. Packaging does not copy generated documents into the source tree. Historical verification reports and ignored reference repositories are not bundled.

The Skill format and several bundled Skills derive from Nanobot's OpenClaw-compatible Skill system. Preserve applicable upstream attribution and third-party notices.
