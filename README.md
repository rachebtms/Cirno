# Cirno

Cirno is a general-purpose AI assistant with a Python service and a React/TypeScript browser interface, built for personal assistance and sustained research.

Conversations have separate histories, input queues, Goals and cancellation scopes. The Router (default `@cirno`) handles brief checks directly, delegates medium and large tasks to ordinary conversations and presents reports. Projects group conversations independently of their working directories. Memory, profiles and learned Skills live in Agent Home.

## Run from source

Requires Python 3.11+ and Node.js 24 for the frontend build. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
python -m pip install -e sources/cirno-memory -e sources/cirno-usage -e sources/cirno-vault -e sources/cirno-core -e sources/cirno-server -e .
cirno --port 8000
```

Open `http://localhost:8000` and configure a connection under Settings → Providers, then add a model under Settings → Models. On first launch, register the instance owner, choose the Router’s display @name (default `@cirno`), and configure a model in the browser. Data defaults to `~/.cirno/`; use `cirno --home /path/to/instance` for a separate instance. See [configuration](documents/configuration.md).

The new-conversation header offers optional [PTC mode](documents/architecture/ptc.md), which lets the model compose tool calls inside a bounded Python program. It is off by default and saved per conversation.

## Docker

Run the published image:

```sh
docker compose up -d
docker compose logs cirno
```

Open `http://localhost:8765`. On a new instance, register your instance owner in the browser, then configure a model. No generated password or setup code needs to be copied from logs. The mounted `~/.cirno` holds `config.json`, Agent Home in `home/`, runtime data in `state/` and the default `workspace/`. Optional embeddings are disabled by default.

The [GitHub Actions workflow](.github/workflows/container.yml) is configured to verify, build and publish Linux AMD64/ARM64 images to `ghcr.io/rachebtms/cirno`. Publication requires committed code, a pushed trigger and a successful workflow. Compose uses the published image without a local build. See [container deployment and publishing](documents/docker.md).

Use `docker compose -f compose.yaml -f compose.full.yaml up -d` for the `latest-full` variant, which includes Telegram dependencies, CLI tools, Homebrew and optional embedding weights. Embedding inference remains disabled by default.

## Repository and documentation

- `sources/cirno-core/`: execution engine, model providers, memory coordination, tools, Skills and session state.
- `sources/cirno-memory/`, `sources/cirno-usage/`, `sources/cirno-vault/`: memory retrieval, usage accounting and encrypted credentials.
- `sources/cirno-server/`: HTTP/WebSocket API, Telegram, service lifecycle and settings.
- `sources/cirno/`: lightweight application distribution and public SDK facade.
- `sources/cirno-web/`: browser client and client contracts.
- `documents/`: current English user and developer guides.
- `references/`: ignored local references, archived implementations and verification records.

Start with the [documentation index](documents/README.md). It covers [memory](documents/architecture/memory.md), [Goals and coordination](documents/goals-and-dream.md), [routing and Stop](documents/development/conversation-routing.md) and the [source layout](documents/development/source-layout.md).

## Releases

The current version is **0.2.4**. See the [release notes](documents/releases/0.2.4.md). Instances on 0.1.6, 0.2.0, 0.2.1, 0.2.2 or 0.2.3 are automatically migrated at startup while retaining their instance volume. See [instance migration](documents/migrations.md) and the [Docker upgrade steps](documents/docker.md#upgrading-from-016).

## Acknowledgements and updates

Cirno draws on ideas and earlier code from [Nanobot](https://github.com/HKUDS/nanobot), [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness), and [DeepSeek SuperAgent](https://github.com/deepseek-ai/dsh-superagent-prototype). Upstream copyright and third-party notices are preserved in [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Cirno is maintained independently. Update the checkout, rebuild the frontend and reinstall the Python package to upgrade; containers update by rebuilding or pulling a published image. The application retains service restart but has no in-app updater.

The [tabbed workspace guide](documents/workspace.md) covers file editors, local and SSH terminals, request transparency, and encrypted personal credentials in 0.2.4.
