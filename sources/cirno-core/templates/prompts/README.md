# Bundled prompts and Home overrides

The runtime renders templates under `templates/agent/` and loads editable profile files from Home. Ordinary conversations and Cirno have separate reply contracts in `regular_conversation.md` and `cirno_conversation.md`. Tool examples use the current namespaced catalog.

`Home/prompts/dream.md` can override Dream instructions. Run `/dream-prompt init` to create an editable copy of the default. Delete or empty the override to use the bundled instructions again. Dream still enforces its restricted tools, scope and per-input confirmation requirements.

`templates/legacy/SOUL.md` is an exact-match migration fixture. The context builder recognizes an unchanged old Home profile and substitutes the current bundled `SOUL.md` in memory. It is not loaded as current guidance or offered as an editable template. Preserve its exact content so old installations can still be recognized; customized user profiles are retained.
