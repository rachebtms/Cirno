# Source layout

- `sources/cirno-core/`: gateway, agent loop, providers, tools and Python channel adapters.
- `sources/cirno-core/tests/`: runtime tests.
- `sources/cirno-web/src/`: browser interface.
- `sources/cirno-web/channels/`: channel interface contributions and their tests.
- `sources/cirno-web/packages/client-events/`: browser transport contracts.

Run `npm ci`, `npm run typecheck`, `npm test` and `npm run build` from `sources/cirno-web/`. The build writes static assets to `build/webui/`, which the Python package serves and includes in its wheel. Run Python tests from the repository root. Packaging metadata lives in the root `pyproject.toml`; the source directory is installed as the `cirno` package.

Channel manifests declare logical interface entry names. The web build resolves those names from its channel registry; the Python runtime does not require TypeScript source files to be installed.

`cirno` opens the browser interface. `cirno agent --message "..."` supports single requests for scripts. There is no terminal interface or terminal binary distribution.

Only Telegram and Web (WebSocket) channels are included.

Container deployment uses the root `Dockerfile` and `compose.yaml`. The container entrypoint lives in `sources/deployment/`. Contribution instructions are in `documents/development/contributing.md`; the example model configuration is in `documents/examples/config.json`.

## Core modules

The `cirno-core` directory maps directly to the installed `cirno` package. Only `__init__.py` (public exports) and `__main__.py` (entrypoint) live at its root.

| Directory | Responsibility |
| --- | --- |
| `agent/` | Turn execution and tools; `goals/`, `ptc/` and `subagents/` own their execution mechanisms |
| `memory/` | Memory records, split SQLite stores, shared retrieval, embedding worker and Dream/consolidation |
| `skills/` | Discovery, metadata and version history; `builtin/` contains bundled skill documents |
| `runtime/` | Admission, prompt context contracts, process ownership, heartbeat and build identity |
| `sdk/` | Public assistant facade, session/memory clients and streaming types |
| `bus/` | Agent events, channel envelopes, runtime events and delivery contracts |
| `nodes/` | SSH command, transfer and remote job service |
| `notifications/` | Durable notification inbox |
| `storage/` | Small shared instance records such as Projects and Nodes |
| `features/` | Optional dependency installation and feature activation |
| `config/` | Schema, lightweight DTO base, paths, loading and migrations |
| `webui/settings/` | Settings requests, validation, models, capabilities and system operations |
| `webui/mcp/` | MCP presets, configuration endpoints and OAuth adapter |

`channels/`, `providers/`, `session/`, `security/`, `cron/`, `triggers/`, `apps/` and `utils/` retain their domain responsibilities. Internal imports use the owning module directly; there are no files forwarding the removed flat module paths. The public `from cirno import Cirno` interface remains available.

## Development and build files

Shared Python test fixtures live in root `conftest.py`, outside the runtime package. The architecture checker is `sources/development/check_import_boundaries.py`; channel dependency installation is `sources/deployment/install_channel_dependencies.py`. Colocated channel tests and runtime test suites are excluded from release artifacts.

Frontend compilation writes `build/webui/`. Hatch inserts that bundle and document resources into release artifacts directly; the Git revision is staged in a temporary directory. Neither building a wheel nor installing editable mode writes generated files into `sources/cirno-core/`.

Historical review notes and local verification outputs belong in ignored `references/`, rather than the bundled product documentation. Caches, dependency installs and generated assets are ignored by Git.
