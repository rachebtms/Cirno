# Contributing to Cirno

Install development dependencies from the repository root with `python -m pip install -e sources/cirno-memory -e sources/cirno-usage -e sources/cirno-vault -e sources/cirno-core -e sources/cirno-server -e ".[dev]"`. Storage libraries are independently installable under `sources/cirno-memory/`, `sources/cirno-usage/` and `sources/cirno-vault/`. Core and server modules use `sources/cirno-core/src/cirno_core/` and `sources/cirno-server/src/cirno_server/`. The application facade is `cirno`. Run Python checks and focused tests from the repository root.

Use Node.js 24. From `sources/cirno-web/`, run `npm ci`, `npm run typecheck`, `npm test` and `npm run build`. The browser build writes to `build/webui/` at the repository root.

Commit dependency changes with the lockfile. The KaTeX override keeps Markdown
parsing and rendered math on the same patched version; the minimatch and CSS
selector-parser overrides patch transitive development dependencies. Recheck
`npm audit`, math/code rendering and browser interactions when updating them.

Keep execution and client state scoped to the conversation and turn that owns it. Tests use isolated Home directories. Agent personality, memory and user Skills belong to Home; project directories contain project content. Preserve upstream license and third-party notices.

Tool operation names and conversation-level selection are described in
[Tool namespaces](../architecture/tools.md). Keep settings and agent tools on
shared domain services, rather than maintaining separate retrieval or validation
implementations.

## Checks

From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run typecheck
npm --prefix sources/cirno-web run lint
npm --prefix sources/cirno-web test
npm --prefix sources/cirno-web run build
python sources/deployment/install_channel_dependencies.py --all-channels
python sources/development/check_import_boundaries.py
python -m ruff check sources/cirno-memory sources/cirno-usage sources/cirno-vault sources/cirno-core sources/cirno-server --select F --exclude tests
python -m pytest -q -n 2
```

Use focused tests during development and the full checks for release changes. Release tests install the real wheels outside the checkout and serve their bundled Web UI. Run browser layout and interaction checks with `npm --prefix sources/cirno-web run test:browser` after installing Playwright Chromium. Test output and local performance records belong in ignored `references/`, not current product guides. Run `cirno` for the backend and `npm --prefix sources/cirno-web run dev` for frontend hot reload.

`npm --prefix sources/cirno-web run gallery` opens the standalone component
gallery. Its `lang` and `theme` URL parameters preserve view choices without
changing instance preferences. Browser component tests use the shared preference
driver and simulated server connection; application tests use the authenticated
service contracts. Do not seed removed product preference keys in local storage.

## Documentation

Maintained documentation and bundled instructions are in English. Verify names, paths, defaults and permissions against the current implementation. Keep model-facing tool names aligned with `agent/tools/names.json`. Historical implementation notes are not product contracts and must not be bundled as current guidance. Preserve original third-party licenses and multilingual test fixtures.
