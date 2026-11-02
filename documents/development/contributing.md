# Contributing to Cirno

Install development dependencies from the repository root with `python -m pip install -e sources/cirno-core -e sources/cirno-server -e ".[dev]"`. Core and server modules are organized under `sources/cirno-core/` and `sources/cirno-server/`, installed as `cirno_core` and `cirno_server`. The application facade is `cirno`. Run Python checks and focused tests from the repository root.

From `sources/cirno-web/`, run `npm ci`, `npm run typecheck`, `npm test` and `npm run build`. The browser build writes to `build/webui/` at the repository root.

Keep execution and client state scoped to the conversation and turn that owns it. Tests use isolated Home directories. Profile, memory and user Skills belong to Home; project directories contain project content. Preserve upstream license and third-party notices.

Tool operation names and conversation-level selection are described in
[Tool namespaces](../architecture/tools.md). Keep settings and agent tools on
shared domain services, rather than maintaining separate retrieval or validation
implementations.

## Checks

From the repository root:

```sh
python sources/deployment/install_channel_dependencies.py --all-channels
python sources/development/check_import_boundaries.py
python -m ruff check sources/cirno-core sources/cirno-server --select F --exclude tests
python -m pytest
npm --prefix sources/cirno-web run typecheck
npm --prefix sources/cirno-web run lint
npm --prefix sources/cirno-web test
npm --prefix sources/cirno-web run build
```

Use focused tests during development and the full checks for release changes. Test output and local performance records belong in ignored `references/`, not current product guides. Run `cirno` for the backend and `npm --prefix sources/cirno-web run dev` for frontend hot reload.

## Documentation

Maintained documentation and bundled instructions are in English. Verify names, paths, defaults and permissions against the current implementation. Keep model-facing tool names aligned with `agent/tools/names.json`. Historical implementation notes are not product contracts and must not be bundled as current guidance. Preserve original third-party licenses and multilingual test fixtures.
