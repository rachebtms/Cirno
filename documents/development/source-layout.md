# Source layout

Cirno has three Python distributions and one browser frontend. They run as one
service and share one release version; package boundaries do not create extra
processes or network services.

| Source | Installed package | Responsibility |
| --- | --- | --- |
| `sources/cirno-core/` | `cirno_core` (`cirno-core`) | Agent execution, Goals, PTC, providers, tools, memory, Skills, durable sessions and domain services |
| `sources/cirno-server/` | `cirno_server` (`cirno-server`) | HTTP/WebSocket API, authentication, settings, Telegram, optional channel dependencies and service lifecycle |
| `sources/cirno/` | `cirno` (`cirno-ai`) | Small installation entry and public `from cirno import Cirno` SDK facade |
| `sources/cirno-web/` | Browser bundle | React/TypeScript interface, channel UI contributions and client transport contracts |

The dependency direction is `cirno-ai → cirno-server → cirno-core`. The core must
not import the server or application facade. Shared history projection, turn
recovery and the personal Cirno session initializer belong to `core/session/`;
HTTP routes and channel adapters consume them. Package ownership is checked by
`sources/development/check_import_boundaries.py`.

Each Python distribution has its own `pyproject.toml` and wheel. The core and
server source directories map directly to their installed package names; source
files are not nested in another copy of the same directory. There are no old
import-path forwarding modules.

## Core domains

- `agent/`: execution, Goals, PTC, subagents and tools.
- `memory/`: knowledge, split SQLite stores, retrieval, embeddings and Dream.
- `session/`: durable state, display history, recovery and turn ownership.
- `providers/`: model transports, authentication and provider catalogs.
- `config/`, `security/`, `runtime/`, `bus/`: configuration, permissions, execution contracts and events.
- `skills/`, `nodes/`, `notifications/`, `storage/`: Skills/history, SSH operations, Inbox and instance records.
- `cron/`, `triggers/`, `apps/`, `sdk/`, `utils/`: scheduling, wakeups, CLI Apps, SDK and shared utilities.

## Build and development

Install the local distributions together from the repository root:

```sh
python -m pip install -e sources/cirno-core -e sources/cirno-server -e ".[dev]"
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
cirno
```

`cirno` starts the complete service in the foreground. Initial owner registration
and model configuration take place in the browser. There are no separate
`gateway`, `webui`, terminal agent or terminal onboarding commands. A supervisor
or Docker handles background execution.

Frontend compilation writes `build/webui/`. The server wheel embeds that bundle;
the core wheel embeds the current documentation in its documentation Skill.
Build hooks stage generated resources without writing them into the source tree.
Source distributions contain the resources needed to rebuild their own wheels.

Root `conftest.py` contains shared test fixtures. Core tests, server tests and
colocated channel tests run from the repository root and are excluded from
release wheels. Only Web (WebSocket) and personal Telegram channels are bundled.
Container files live at the repository root and in `sources/deployment/`.

Historical research, verification output and runtime samples belong in ignored
`references/`. Current English product guides live in `documents/`.
