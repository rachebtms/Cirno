# Docker deployment and publishing

The repository workflow `.github/workflows/container.yml` is configured to verify, build and publish images to `ghcr.io/rachebtms/cirno`. A local workflow file is not evidence that an image has already been published.

## Publication

- Pull requests run frontend and backend checks and build an AMD64 image for a startup smoke test. They do not log in to the registry or publish.
- Pushes to `main` publish `main`, `latest` and a commit tag after verification succeeds.
- Version tags such as `v0.1.0` publish version and major/minor tags. Prerelease tags stay identifiable by their full version.
- `workflow_dispatch` allows a manual run from the Actions page.
- Published images support `linux/amd64` and `linux/arm64`.

Publication uses the workflow's `GITHUB_TOKEN` with `packages: write`; no Docker Hub password or personal access token is needed. OCI source labels associate the package with this repository. If the package is initially private, make it public in the GitHub package settings to allow anonymous server pulls.

The code and workflow must first be committed and pushed to GitHub. A workflow file present only in a local checkout does not start Actions. The checks job is a release gate: test failures prevent the container publication job from running.

## Deploy

Build a source checkout using the repository's `compose.yaml`:

```sh
docker compose up -d --build
docker compose logs cirno-gateway
```

Once the workflow has published an image, use `docker compose pull` followed by `docker compose up -d` to deploy it without a local build.

Open `http://localhost:8765` and use the password printed when a new Home is initialized. Configure providers through the Web UI. The Home directory is mounted from `~/.cirno`; it contains configuration, profiles, memory, skills and runtime records. Existing configuration is preserved on restart.

Pin an image with `CIRNO_IMAGE_TAG=0.1.0`, or track `latest`. `CIRNO_MEMORY_LIMIT` defaults to `400M`. Optional memory embeddings are disabled by default. A container image build does not bundle an embedding model.

To update a registry deployment, pull the selected image tag and recreate the service. For a source deployment, update the checkout and run `docker compose up -d --build` again.

The workflow smoke test starts the server within a 400MB limit, checks its health endpoint and Web UI, and verifies that PID 1 runs as the non-root Cirno user. ARM64 is built for publication; the startup smoke test runs on AMD64.

## Networking and authentication

Compose publishes the Web interface on port 8765 and binds the gateway health port 18790 to loopback. `CIRNO_WEB_TOKEN` selects the initial Web password for a new Home; otherwise bootstrap generates one and prints it. Bootstrap preserves an existing `config.json`, so changing that environment variable does not reset an existing password. Configure model credentials in the browser or reference environment variables in configuration.

The entrypoint fixes ownership of the mounted Home and drops to the Cirno user. Full Access refers to the container's files and processes, including explicitly mounted paths. `compose.bwrap.yaml` is an optional override for the Bubblewrap command sandbox; it adds privileges and unconfines AppArmor/seccomp for that mode. The default Compose configuration does not use that override.
