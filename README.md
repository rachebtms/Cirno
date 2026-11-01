# Cirno

Cirno is a general-purpose AI assistant with a Python gateway and a React/TypeScript browser interface, based on [Nanobot](https://github.com/HKUDS/nanobot).

Conversations have separate histories, input queues, Goals and cancellation scopes. The Cirno coordination conversation delegates execution to ordinary conversations and presents reports. Projects group conversations independently of their working directories. Memory, profiles and learned Skills live in Agent Home.

## Run from source

Requires Python 3.11+ and Node.js 24 for the frontend build. From the repository root:

```sh
npm --prefix sources/cirno-web ci
npm --prefix sources/cirno-web run build
python -m pip install -e .
cirno webui --port 8000
```

Open `http://localhost:8000` and configure a provider under Settings → Models. The initial local launch may ask to initialize configuration. Data defaults to `~/.cirno/`; use `cirno --home /path/to/instance webui` for a separate instance. See [configuration](documents/configuration.md).

The new-conversation header offers optional [PTC mode](documents/architecture/ptc.md), which lets the model compose tool calls inside a bounded Python program. It is off by default and saved per conversation.

## Docker

Build the checkout locally:

```sh
docker compose up -d --build
docker compose logs cirno-gateway
```

Open `http://localhost:8765`. On a new Home, register your instance owner in the browser, then configure a model. No generated password or setup code needs to be copied from logs. Configuration and durable state persist in the mounted `~/.cirno`. The Compose memory limit defaults to `400M`; optional embeddings are disabled.

The [GitHub Actions workflow](.github/workflows/container.yml) is configured to verify, build and publish Linux AMD64/ARM64 images to `ghcr.io/rachebtms/cirno`. Publication requires committed code, a pushed trigger and a successful workflow. After an image is published, deployments can pull it instead of building locally. See [container deployment and publishing](documents/docker.md).

## Repository and documentation

- `sources/cirno-core/`: Python runtime, bundled Skills, prompts and tests.
- `sources/cirno-web/`: browser client and client contracts.
- `documents/`: current English user and developer guides.
- `references/`: ignored local references, archived implementations and verification records.

Start with the [documentation index](documents/README.md). It covers [memory](documents/architecture/memory.md), [Goals and coordination](documents/goals-and-dream.md), [routing and Stop](documents/development/conversation-routing.md) and the [source layout](documents/development/source-layout.md).

## Attribution and updates

This fork starts from Nanobot commit `1c28b20c7e11c06b5f589259e62be238da387b11`. Upstream copyright and third-party notices are preserved in [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Cirno is maintained independently. Update the checkout, rebuild the frontend and reinstall the Python package to upgrade; containers update by rebuilding or pulling a published image. The application retains service restart but has no in-app updater.
