---
name: skill-creator
description: Create, update, validate or package reusable Cirno Skills in Agent Home.
---

# Skill Creator

A Skill is a directory containing `SKILL.md` and only the resources needed to perform its workflow. Store user Skills at `<Home>/skills/<name>/`, never in a task workspace. Use the Home path supplied by Runtime Context; `~/.cirno` is only the default.

## Plan the Skill

Use a concrete task to identify reusable steps, inputs, checks and outputs. Read overlapping Skills first. Keep one-off facts in memory rather than making a Skill. Dream may extract a workflow only after it appears in at least two independent tasks; repeated summaries of one task do not count as independent evidence.

Keep instructions concise. Put essential workflow rules in `SKILL.md`, optional detail in `references/`, executable helpers in `scripts/`, and output templates in `assets/`. Reference only resources that actually exist. Use `files__search` to narrow large files before reading them.

## Create and edit

Use the bundled initializer, resolving `scripts/` relative to this Skill's directory:

```sh
python3 scripts/init_skill.py my-skill --path /absolute/cirno-home/skills
python3 scripts/init_skill.py my-skill --path /absolute/cirno-home/skills --resources scripts,references
```

The script creates a directory and starter instructions. Replace placeholders and remove unused generated examples. Edit an existing Skill in place rather than initializing another copy.

Use lowercase letters, digits and hyphens for the name, matching its directory. Frontmatter requires a `name` and a useful `description` explaining the task and when to invoke the Skill. Cirno also supports `metadata` for requirements and `always` for intentional persistent guidance. The body should give actionable steps, tool usage, checks and necessary resource paths. Use the actual namespaced tool catalog; do not invent tool aliases or shell executables from function names.

Test helper scripts on representative inputs. Syntax validation alone does not verify behavior. Preserve sources and uncertainty when the workflow turns evidence into a result.

## Validate and retain history

Run `skills__validate(name="my-skill")` after editing a Home Skill. `skills__history(name="my-skill")` exposes retained versions. File-tool edits and UI deletion preserve Home Skill history; direct external filesystem changes do not have that guarantee. Read historical files when needed and deliberately edit the current version. There is no automatic rollback.

The standalone metadata/resource validator can also run from this Skill's directory:

```sh
python3 scripts/quick_validate.py /absolute/cirno-home/skills/my-skill
```

## Package when requested

Packaging is optional for local discovery. To share a Skill:

```sh
python3 scripts/package_skill.py /absolute/cirno-home/skills/my-skill /absolute/output
```

The helper validates and writes a `.skill` ZIP archive. It rejects symlinks. Fix validation errors before packaging; do not treat successful packaging as a behavioral test of included scripts.
