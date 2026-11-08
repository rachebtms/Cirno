# Bundled prompts and Home overrides

The runtime renders templates under `templates/agent/` and loads editable profile files from Home. Ordinary conversations and Cirno have separate reply contracts in `regular_conversation.md` and `router_conversation.md`. Tool examples use the current namespaced catalog.

`Home/prompts/dream.md` can override Dream instructions. Run `/dream-prompt init` to create an editable copy of the default. Delete or empty the override to use the bundled instructions again. Dream still enforces its restricted tools, scope and per-input confirmation requirements.

Profile files are loaded directly from the instance's `home/` directory. This release has no legacy profile importer or automatic migration of earlier instance layouts.
