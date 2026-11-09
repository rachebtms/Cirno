# Bundled prompts and Home overrides

The runtime renders templates under `templates/agent/` and loads editable profile files from Home. Workers and the Router have separate reply contracts in `regular_conversation.md` and `router_conversation.md`. Tool examples use the current namespaced catalog.

Settings → Personality adds editable shared, Router-only and Worker-only system instructions after the built-in contract and profiles. These are captured once per turn and do not replace role/tool permissions or execution budgets. Empty fields add nothing. Transient Worker subagents receive shared and Worker additions. Internal maintenance uses `maintenance_context.md`, treats profiles as reference data and does not receive conversation additions.

`Home/prompts/dream.md` can override Dream instructions. Run `/dream-prompt init` to create an editable copy of the default. Delete or empty the override to use the bundled instructions again. Dream still enforces its restricted tools, scope and per-input confirmation requirements.

Profile files are loaded directly from the instance's `home/` directory. New owner registration seeds `BOOTSTRAP.md` for the Router's first introduction. The Router saves agreed details to `SOUL.md` and `USER.md`, then empties the bootstrap file. Login and ordinary session creation do not recreate it. Published v0.1.6 instances use the automatic instance migration described in the documentation.
