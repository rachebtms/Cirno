# Docker deployment and publishing

The repository workflow `.github/workflows/container.yml` is configured to verify, build and publish images to `ghcr.io/rachebtms/cirno`. A local workflow file is not evidence that an image has already been published.

## Publication

- Pull requests run frontend and backend checks and build an AMD64 image for a startup smoke test. They do not log in to the registry or publish.
- Pushes to `main` publish `main`, `latest` and a commit tag after verification succeeds.
- Version tags such as `v0.1.2` publish version and major/minor tags. Prerelease tags stay identifiable by their full version.
- `workflow_dispatch` allows a manual run from the Actions page.
- Published images support `linux/amd64` and `linux/arm64`.

Publication uses the workflow's `GITHUB_TOKEN` with `packages: write`; no Docker Hub password or personal access token is needed. OCI source labels associate the package with this repository. If the package is initially private, make it public in the GitHub package settings to allow anonymous server pulls.

The code and workflow must first be committed and pushed to GitHub. A workflow file present only in a local checkout does not start Actions. The checks job is a release gate: test failures prevent the container publication job from running.

## Deploy

Use the repository's minimal `compose.yaml` to run the published image:

```sh
docker compose up -d
docker compose logs cirno-gateway
```

The example publishes only the Web UI port and persists Home. Model providers, Telegram and other features are configured in the browser. There are no default CPU or memory limits.

Open `http://localhost:8765`. On a new Home, the Web UI asks you to register the instance owner with a username and password (at least 10 characters, including an uppercase letter and a symbol). Registration closes after that account is created. The next page configures model providers and model configurations; this step can be deferred to Settings. No terminal setup code or generated password is required. The Home directory is mounted from `~/.cirno`; it contains configuration, profiles, memory, skills and runtime records. Existing configuration is preserved on restart.

To pin a release, change the image to `ghcr.io/rachebtms/cirno:0.1.2`; otherwise track `latest`. Optional memory embeddings are disabled by default. A container image build does not bundle an embedding model.

To update a registry deployment, pull the selected image tag and recreate the service. To build from a checkout instead, run `docker build -t cirno:local .` and change the Compose image to `cirno:local`.

The workflow smoke test starts the server, checks its health endpoint and Web UI, and verifies that PID 1 runs as the non-root Cirno user. ARM64 is built for publication; the startup smoke test runs on AMD64.

## Networking and authentication

Compose publishes the Web interface on port 8765. The gateway health endpoint stays inside the container. New instances enable `channels.websocket.browserSetup` and use browser registration. The first person to register becomes the instance owner: keep a new deployment private until you have registered, and use HTTPS when sending credentials over an untrusted network.

Owner credentials and browser sessions are stored in `webui-auth.sqlite3` beside the instance configuration, outside the workspace. Passwords use salted scrypt hashes; session tokens are also hashed in storage. Login uses an HttpOnly, SameSite=Strict cookie with a 30-day lifetime. Signing out revokes that browser session. The account, sessions and onboarding progress survive service restarts.

An explicitly supplied `CIRNO_WEB_TOKEN` retains shared-password authentication for a new Home instead of browser registration. Existing `config.json` files keep their previous authentication mode. Changing that environment variable does not reset an existing account or password. Configure model credentials in the browser or reference environment variables in configuration.

The entrypoint fixes ownership of the mounted Home and drops to the Cirno user. Full Access refers to the container's files and processes, including explicitly mounted paths. `compose.bwrap.yaml` is an optional override for the Bubblewrap command sandbox; it adds privileges and unconfines AppArmor/seccomp for that mode. The default Compose configuration does not use that override.
