---
name: clawhub
description: Search and install agent skills from ClawHub, the public skill registry.
homepage: https://clawhub.ai
metadata: {"cirno":{"emoji":"🦞"}}
---

# ClawHub

Public skill registry for AI agents. Search by natural language (vector search).

## When to use

Use this skill when the user asks any of:
- "find a skill for …"
- "search for skills"
- "install a skill"
- "what skills are available?"
- "update my skills"

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.cirno
```

Replace `<slug>` with the skill name from search results. This places the skill into `~/.cirno/skills/`, where Cirno discovers Home Skills. Always include `--workdir`. If the instance uses a custom Home, replace `~/.cirno` with that exact Home path in every command. Never install into the project workspace.

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.cirno
```

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.cirno
```

## Notes

- Requires Node.js (`npx` comes with it).
- No API key needed for search and install.
- Login (`npx --yes clawhub@latest login`) is only required for publishing.
- `--workdir ~/.cirno` is critical — without it, skills install to the current directory instead of Cirno Home.
- After installation, use `skills__validate` for the installed name and check that it appears in the available Skill list. Do not claim installation succeeded before verifying the files and validation result.
