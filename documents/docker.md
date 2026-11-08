# Docker deployment and publishing

The repository workflow `.github/workflows/container.yml` verifies, builds and publishes images to `ghcr.io/rachebtms/cirno`.

## Publication

- Pull requests run frontend and backend checks and build AMD64 and ARM64 images on native runners for startup smoke tests. They do not log in to the registry or publish.
- Pushes to `main` publish `main`, `latest` and a commit tag after verification succeeds.
- Version tags such as `v0.2.0` publish version and major/minor tags. Prerelease tags stay identifiable by their full version.
- `workflow_dispatch` allows a manual run from the Actions page.
- Published images support `linux/amd64` and `linux/arm64`.

Publication uses the workflow's `GITHUB_TOKEN` with `packages: write`; no Docker Hub password or personal access token is needed. OCI source labels associate the package with this repository. If the package is initially private, make it public in the GitHub package settings to allow anonymous server pulls.

The checks job is a release gate: test failures prevent container builds. AMD64 and ARM64 images build in parallel on `ubuntu-24.04` and `ubuntu-24.04-arm`. Each image must pass startup verification before its digest is uploaded. A final job publishes the multi-platform manifest only after both architectures succeed.

Backend tests run with two workers, and Python dependency downloads are cached alongside the existing npm and Docker build caches. The architecture-independent browser bundle builds on the build host's native architecture. CI uses native runners for both architectures and does not use QEMU.

## Deploy

Use the repository's minimal `compose.yaml` to run the published image:

```sh
docker compose up -d
docker compose logs cirno
```

The example publishes only the Web UI port and persists the instance root. Model providers, Telegram and other features are configured in the browser. There are no default CPU or memory limits.

Open `http://localhost:8765`. On a new instance, the Web UI asks you to register the instance owner with a username and password (at least 10 characters, including an uppercase letter and a symbol). Registration closes after that account is created. The next page configures model providers and model configurations; this step can be deferred to Settings. No terminal setup code or generated password is required. The instance root is mounted from `~/.cirno`: `config.json` holds configuration, `home/` holds profiles, memory and Skills, `state/` holds runtime data, and `workspace/` is the default task directory. Existing configuration is preserved on restart.

To pin a release, change the image to `ghcr.io/rachebtms/cirno:0.2.0`; otherwise track `latest`. Optional memory embeddings are disabled by default. The default slim image does not bundle an embedding model; the full variant includes matching INT8 weights and a tokenizer, with inference still disabled by default.

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
2. Change the Compose image to `ghcr.io/rachebtms/cirno:0.2.0`, or `ghcr.io/rachebtms/cirno:0.2.0-full` for the full variant. Preserve your volumes, ports, environment and reverse-proxy network configuration.
3. Pull and recreate the service:

   ```sh
   docker compose pull cirno
   docker compose up -d cirno
   docker compose logs --tail=100 cirno
   ```

   If you use Compose overrides, pass the same `-f` files to each command. With `compose.full.yaml`, set the pinned full-image tag in that override because it takes precedence over the base file.

4. Refresh the browser or installed Web app and check Settings → About for 0.2.0. Sign in with the existing account.

Recreating the container interrupts its current process; do this between active operations. Saved progress remains in the instance volume. Packages and files written only into the old container's writable layer do not survive replacement. The full image supplies the bundled tools and persists user Python packages and supported CLI configuration for subsequent recreations. Do not delete or replace the existing instance volume during an upgrade.

## Full image

The default `latest` image stays small. `latest-full` adds preinstalled tools and optional feature dependencies. Both variants use the same Cirno source and startup behavior, run the agent as UID 1000, and support AMD64 and ARM64 through native runners. Release tags produce matching `VERSION` and `VERSION-full` image tags.

Use the existing deployment with the full-image override:

```sh
docker compose -f compose.yaml -f compose.full.yaml up -d
```

The full image includes:

| Purpose | Commands |
| --- | --- |
| Development | `git`, `git-lfs`, `gh`, `tea`, `go` |
| Network and SSH | `curl`, `wget`, `ssh`, `scp`, `sftp`, `rsync`, `rclone` |
| Terminal and files | `tmux`, `rg`, `fd`, `fzf`, `bat`, `jq`, `yq`, `tree` |
| Python | `python3`, `pipx`, `uv`, `uvx`, `hf` |
| Node | `node`, `npm`, `npx`, `bun`, `nvm` (shell function) |
| Agent integrations | `summarize` (Homebrew), `mcporter`, `gog`, `xurl` |
| Documents and media | `ffmpeg`, `yt-dlp`, `pandoc`, `pdftotext`, `tesseract` |
| Storage and package management | `sqlite3`, `brew` |

Telegram dependencies and the available Python optional feature extras are installed at image build time. This does not enable Telegram or configure third-party accounts: bot tokens and CLI authorizations remain instance-specific. Authenticated Web UI installation and skill management work through reverse proxies and remote browsers; there is no localhost-only installation policy or remote-install opt-in.

The full image bundles `Xenova/bge-small-zh-v1.5` at revision `75c43b069aac4d136ba6bc1122f995fedcfd2781`, including `model_quantized.onnx`, `tokenizer.json`, its model card and the upstream MIT license. Downloads are checked against SHA-256 hashes. Blank model and tokenizer paths select these bundled assets, including when replacing a slim container; custom paths take precedence. Embeddings remain disabled until explicitly enabled. The weights live at `/opt/cirno/models/bge-small-zh-v1.5`, outside the mounted instance and workspace, and the selected paths appear under Memory retrieval.

The additional commands consume image disk space; they do not run background daemons at startup. The CI smoke test checks command execution as the non-root user, Telegram dependency availability, and actual CPU inference with the bundled model on both architectures.

The normal instance volume also persists CLI configuration under `state/cli/` and user-installed Python, npm, uv, pipx, Go, Bun and nvm tools under `state/tools/`. In the full image, `python`, `python3`, `pip` and `uv pip` use a separate virtual environment at `/home/cirno/.cirno/state/tools/python`; packages installed there survive container recreation. Cirno itself uses `/app/.venv`, so user packages do not replace the service's dependencies. Interpreter links are refreshed at startup while retaining user packages.

Gitea `tea` login configuration is stored under `state/cli/config/tea/`, GitHub `gh` configuration under `state/cli/config/gh/`, and the npm user configuration under `state/cli/config/npmrc`. XDG configuration, data and caches also point into the instance volume. Keep that volume when recreating the container to retain credentials and user packages. The native full-image smoke tests install a local Python package and a fixture Gitea login, recreate the container with the same volume, and verify both survive.

`nvm` is loaded for Bash commands, including the agent's non-interactive shell. New Homebrew installations or explicit changes inside `/app/.venv` belong to the container layer and are lost on recreation: add those to a derived image rather than treating the running container as the package source. Preinstalled full-image tools are restored from the image whenever the container is recreated.

Full builds have separate per-architecture caches. The tool layer is built before Cirno sources are copied, so an application change does not reinstall the whole tool collection.

## Networking and authentication

Compose publishes the Web interface on port 8765. The server health endpoint stays inside the container. New instances enable `channels.websocket.browserSetup` and use browser registration. The first person to register becomes the instance owner: keep a new deployment private until you have registered, and use HTTPS when sending credentials over an untrusted network.

Owner credentials and browser sessions are stored in `state/webui-auth.sqlite3` under the instance root, outside the workspace. Passwords use salted scrypt hashes; session tokens are also hashed in storage. Login uses an HttpOnly, SameSite=Strict cookie with a 30-day lifetime. Signing out revokes that browser session. The account, sessions and onboarding progress survive service restarts.

An explicitly supplied `CIRNO_WEB_TOKEN` retains shared-password authentication for a new instance instead of browser registration. Existing `config.json` files keep their previous authentication mode. Changing that environment variable does not reset an existing account or password. Configure model credentials in the browser or reference environment variables in configuration.

The entrypoint fixes ownership of the mounted instance root and drops to the Cirno user. Full Access refers to the container's files and processes, including explicitly mounted paths. `compose.bwrap.yaml` is an optional override for the Bubblewrap command sandbox; it adds privileges and unconfines AppArmor/seccomp for that mode. The default Compose configuration does not use that override.

## Complete backups

The Web UI includes [Backup & restore](backups.md). It archives the instance and selected external folders; historical workspaces and common CLI credential/package directories are suggested automatically. It is included in both v0.2.0 image variants.

CLI Apps in the full image use the same persistent user Python environment and non-secret directory environment as shell tools. This keeps market-installed Python packages and tools using XDG, npm, uv or pipx paths inside the instance volume. CLI processes do not inherit provider API keys. SSH, Git credential files, `.aws`, `.cargo` and `.local` locations are also linked into instance storage on a fresh full-image container. Existing external locations are offered as optional backup paths.
