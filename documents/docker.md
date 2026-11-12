# Docker deployment and publishing

The repository workflow `.github/workflows/container.yml` verifies, builds and publishes images to `ghcr.io/rachebtms/cirno`.

## Publication

- Pull requests run frontend and backend checks and build AMD64 and ARM64 images on native runners for startup smoke tests. They do not log in to the registry or publish.
- Pushes to `main` publish `main`, `latest` and a commit tag after verification succeeds.
- Version tags such as `v0.2.12` publish version and major/minor tags. Prerelease tags stay identifiable by their full version.
- `workflow_dispatch` allows a manual run from the Actions page.
- Published images support `linux/amd64` and `linux/arm64`.

Publication uses the workflow's `GITHUB_TOKEN` with `packages: write`; no Docker Hub password or personal access token is needed. OCI source labels associate the package with this repository. If the package is initially private, make it public in the GitHub package settings to allow anonymous server pulls.

The checks job is a release gate: test failures prevent container builds. AMD64 and ARM64 images build in parallel on `ubuntu-24.04` and `ubuntu-24.04-arm`. Each image must pass startup verification before its digest is uploaded. A final job publishes the multi-platform manifest only after both architectures succeed.

Backend tests run with two workers, and Python dependency downloads are cached alongside the existing npm and Docker build caches. The architecture-independent browser bundle builds on the build host's native architecture. CI uses native runners for both architectures and does not use QEMU.

The CI runner and BuildKit use Cloudflare DNS for package-repository resolution after the runner's default upstream failed to resolve Ubuntu domains. Builds and smoke-test containers retain normal Docker networking. This CI configuration does not change DNS or software sources in user deployments.

## Deploy

Use the repository's minimal `compose.yaml` to run the published image:

```sh
docker compose up -d
docker compose logs cirno
```

The example publishes only the Web UI port and persists the instance root. Model providers, Telegram and other features are configured in the browser. There are no default CPU or memory limits.

Open `http://localhost:8765`. On a new instance, the Web UI asks you to register the instance owner with a username and password (at least 10 characters, including an uppercase letter and a symbol). Registration closes after that account is created. Setup then offers theme selection and model provider/model configuration; model setup can be deferred to Settings. With a model connected, the Router starts a one-time introduction to learn its personality and how to address the owner. No terminal setup code or generated password is required. The instance root is mounted from `~/.cirno`: `config.json` holds configuration, `home/` holds profiles, memory and Skills, `state/` holds runtime data, and `workspace/` is the default task directory. Existing configuration is preserved on restart.

To pin a release, change the image to `ghcr.io/rachebtms/cirno:0.2.12`; otherwise track `latest`. Optional memory embeddings are disabled by default. The unified image installs optional tool and embedding components only when selected. Embedding inference stays disabled by default.

To update a registry deployment, pull the selected image tag and recreate the service. To build from a checkout instead, run `docker build -t cirno:local .` and change the Compose image to `cirno:local`.

The workflow smoke test starts the server, checks its health endpoint and Web UI, and verifies that PID 1 runs as the non-root Cirno user. Startup, registration and Web UI checks run on both AMD64 and ARM64.

## Upgrading from 0.1.6

Keep the same instance mount (`~/.cirno:/home/cirno/.cirno` in the example).
Startup automatically imports 0.1.6 conversation and automation state, updates
configured service paths to `/v0/`, and records `lastRunVersion`. Your account
remains registered. Originals and a migration report stay in the instance;
see [instance migration](migrations.md). Older layouts should first be upgraded
to 0.1.6.

Update external clients, reverse-proxy path rules, MCP OAuth redirect
registrations and custom health checks to the [versioned endpoints](development/api.md).
The browser entry stays at `/`.

1. Stop the service and back up the entire mounted instance directory. Also back up workspaces mounted outside that directory.
2. Change the Compose image to `ghcr.io/rachebtms/cirno:0.2.12`. Preserve your volumes, ports, environment and reverse-proxy network configuration.
3. Pull and recreate the service:

   ```sh
   docker compose pull cirno
   docker compose up -d cirno
   docker compose logs --tail=100 cirno
   ```

   If you use Compose overrides, pass the same `-f` files to each command. Optional tools are selected by Compose command-line arguments; there is no separate full/slim build or `-full` tag in the unified publishing workflow.

4. Refresh the browser or installed Web app and check Settings → About for 0.2.12. Sign in with the existing account.

Recreating the container interrupts its current process; do this between active operations. Saved progress remains in the instance volume. Packages and files written only into the old container's writable layer do not survive replacement. Selected setup components restore their required dependencies and reuse persistent tool packages and CLI configuration. Do not delete or replace the existing instance volume during an upgrade.

## One image, selectable environments

The Dockerfile and publishing workflow now produce one image for each architecture. The base contains Cirno, `cirno-setup`, Python/uv, Node/npm/npx and minimum service prerequisites. Standard uvx/npx MCP launch and CLI package installation do not require the research preset. LibreOffice, LaTeX, browser libraries and development tools are optional startup components rather than preinstalled image contents.

Use the research/operations/document preset with the same image:

```sh
docker compose -f compose.yaml -f compose.rachebtms.yaml up -d
```

The override sets `command: ["+presets.rachebtms", "--timeout", "1800", "--verify"]`. The image entrypoint is `cirno-setup --serve`: it installs and verifies the command-line selections, drops privileges, checks the service environment and then replaces itself with Cirno. `--verify` rechecks all selected dependencies after installation; `+rachebtms` is shorthand for this preset. Installation failures stop startup and are visible in container logs. Health becomes ready only after setup and service startup complete.

A minimal Compose service omits `command` entirely. To choose individual components:

```yaml
services:
  cirno:
    command: ["+pip.pytest", "+system.libreoffice", "--timeout", "1800"]
```

Installer options come before `--`; Cirno server arguments come after it, e.g. `command: ["+pip.pytest", "--timeout", "300", "--", "--port", "8765"]`. Package selections and installer timeout are not application settings and are never saved to `config.json`. Every recreation gets its selections from Compose. Existing installation receipts and caches record completed work, not a desired component list.

For installation and verification without a setup command time limit, use `command: ["+presets.rachebtms", "--timeout", "0", "--verify"]`. Zero disables setup's installation and readiness-check limits, including the final verification pass; negative values are rejected. The default remains 1800 seconds per installation command, with readiness probes capped at 60 seconds when a positive timeout is selected. Download clients and package managers retain their own connection and retry rules.

See [environment setup](setup.md) for namespaces, the preset, dependency resolution, privilege separation, caching and adding recipes. The former `-full` image tags are historical releases; they are no longer generated. When moving from an older full deployment, use the unified image with `+presets.rachebtms` in Compose. Keep the existing instance root; no additional persistent root is required. Previous user packages remain available.

CLI tools keep their configuration and installed packages under `~/.cirno/state`. Compose binds that root plus its `state/tools/homebrew` subdirectory to Homebrew's fixed prefix. Office/LaTeX system files are recreated through APT after container replacement; their archives and additional package list persist within the same root. Service code and the base service Python environment stay in the image.

The native image checks first start the base without optional tools and register an owner, then recreate the same image with the preset command-line arguments and the same data. They verify Office/PDF conversion, XLSX formula recalculation, Pandoc/Lua, default Playwright Chromium screenshots with Chinese fonts, scientific LaTeX/BibTeX, pytest, embedding inference and Python/npm/CLI configuration persistence. An additional APT package is installed and restored in another recreation. Base startup is checked at 400 MiB; research/rendering checks use 1 GiB. Both CPU architectures build natively.

## Full catalogue validation

`command: ["+all", "--verify", "--timeout", "3600"]` installs every built-in setup component. This includes the large optional Marker/PyTorch and Manim environments; it is intended primarily for comprehensive CI verification. `+rachebtms` keeps its existing smaller selection.

Both architecture jobs first verify the minimal image, the research preset and persistence after recreation. They then start the same image with `+all --verify`, check Python dependency consistency, exercise the optional CLIs, render SVG, and render a small Manim scene with text and a LaTeX formula. Marker imports and CLI startup are checked without downloading OCR weights or running an inference backend. The exhaustive test uses a 4 GiB container limit and up to one hour for setup; it does not add these packages to the published base image.

## Networking and authentication

Compose publishes the Web interface on port 8765. The server health endpoint stays inside the container. New instances enable `channels.websocket.browserSetup` and use browser registration. The first person to register becomes the instance owner: keep a new deployment private until you have registered, and use HTTPS when sending credentials over an untrusted network.

Owner credentials and browser sessions are stored in `state/webui-auth.sqlite3` under the instance root, outside the workspace. Passwords use salted scrypt hashes; session tokens are also hashed in storage. Login uses an HttpOnly, SameSite=Strict cookie with a 30-day lifetime. Signing out revokes that browser session. The account, sessions and onboarding progress survive service restarts.

An explicitly supplied `CIRNO_WEB_TOKEN` retains shared-password authentication for a new instance instead of browser registration. Existing `config.json` files keep their previous authentication mode. Changing that environment variable does not reset an existing account or password. Configure model credentials in the browser or reference environment variables in configuration.

`cirno-setup` fixes ownership of the mounted instance root and drops to the Cirno user. Full Access refers to the container's files and processes, including explicitly mounted paths. `compose.bwrap.yaml` is an optional override for the Bubblewrap command sandbox; it adds privileges and unconfines AppArmor/seccomp for that mode. The default Compose configuration does not use that override.

## Complete backups

The Web UI includes [Backup & restore](backups.md). It archives the instance and selected external folders; historical workspaces and common CLI credential/package directories are suggested automatically. It is included in the unified image.

CLI Apps use the same persistent user Python environment and non-secret directory environment as shell tools. This keeps market-installed Python packages and tools using XDG, npm, uv or pipx paths inside the instance volume. CLI processes do not inherit provider API keys. SSH, Git credential files, `.aws`, `.cargo` and `.local` locations are also linked into instance storage on a fresh container. Existing external locations are offered as optional backup paths.
