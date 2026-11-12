# Environment setup

`cirno-setup` is an independent Python distribution under `sources/cirno-setup/`, with no dependency on Core, Server or an LLM. Its recipe catalogue and dependency planner serve the CLI and Docker startup. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first outside Docker; the image already includes it. A standalone checkout install is `uv tool install ./sources/cirno-setup`.

## Docker startup

The image entrypoint is `cirno-setup --serve`. It prepares the selected dependencies and verifies the environment before executing the Cirno server. A dependency failure stops startup and reports the error; it never starts a partially prepared server. Root is used for APT and mounted-directory ownership, then setup and Cirno run as the normal user. The server replaces the installer as PID 1 and receives container signals directly.

No optional selections means the minimal environment:

```yaml
services:
  cirno:
    image: ghcr.io/rachebtms/cirno:latest
    environment:
      CIRNO_DOCKER_BOOTSTRAP: "1"
    ports: ["8765:8765"]
    volumes:
      - ~/.cirno:/home/cirno/.cirno
```

The base includes service dependencies for browser setup, model conversations, shell and file tools, disk/keyword memory and the service scheduler. Python/uv, Node/npm/npx, Git and SSH are present. This keeps ordinary uvx- and npx-based MCP servers and CLI installers usable without a preset. Office/LaTeX rendering, browser automation, additional CLI packages, third-party channel SDKs and local vector embeddings are optional components. Configure a model to obtain real model replies; package selection does not provide an API credential.

Choose tools only through Compose's command-line list:

```yaml
services:
  cirno:
    command: ["+presets.rachebtms", "--timeout", "1800"]
```

Or `command: ["+pip.pytest", "+system.libreoffice", "--timeout", "600"]`. The package list and setup options are not in application settings or `config.json`; neither an old `tools.startup` entry nor `CIRNO_SETUP` supplies selections. Changing the Compose list does not uninstall persistent tools automatically.

## CLI

```sh
cirno-setup +pip.pytest +pip.pymupdf
cirno-setup +channels.telegram
cirno-setup +npm.summarize +brew.tea
cirno-setup +rachebtms --verify
cirno-setup +rachebtms --verify --timeout 0
cirno-setup +all --verify --timeout 3600
cirno-setup +presets.rachebtms --dry-run
cirno-setup --list
cirno-setup --serve +pip.pytest --timeout 300 -- --port 8765
```

Standalone invocations install and verify, then exit unless `--serve` is present. `+` is an optional selection prefix, not shell code. Installer options precede `--`; server arguments follow it. `--timeout SECONDS` accepts nonnegative integers and defaults to 1800 seconds per installation command. With a positive value, readiness probes use the smaller of that value and 60 seconds. Set `--timeout 0` to remove setup's command time limits for installation, download transfers, initial readiness checks and final `--verify` checks. Package managers retain their own connection and retry rules. `--proxy URL` configures dependency downloads; standard proxy environment variables also work. `--no-restore-apt` skips restoration of user-added system packages. `--dry-run` prints a dependency plan without changes.

Setup checks installed components and verifies each newly installed dependency by default. `--verify` adds a second serial pass over every selected dependency after all installations finish, including reused components. This catches a later installation breaking an earlier dependency. A failed check reports the component and reason, records a failed status and prevents server startup. `+rachebtms` is shorthand for `+presets.rachebtms`; both expand to the same deduplicated plan. `+all` (alias of `+presets.all`) selects every built-in recipe and its dependencies, including all presets. The catalogue is discovered automatically, so newly added components are covered without updating a separate list. It does not mean every possible third-party pip/npm/APT package. This exhaustive environment is mainly for Actions; ordinary deployments can keep using explicit selections or `+rachebtms`.

Browser readiness also honors `--timeout 0`: its Playwright launch check has no launch deadline in unlimited mode. Positive values retain the browser check's 30-second launch ceiling within the setup probe budget.

Embedding downloads and readiness checks use the same pinned SHA-256 file list, including the model, tokenizer, README and LICENSE. A missing or corrupted file identifies the failed asset and causes setup to repair it before declaring the component ready. Verified files are reused.

Outside Docker, set `CIRNO_SERVICE_PYTHON` to the application environment's Python if setup is installed separately with `uv tool`. This selects the target for service/channel extras and the server executable. Manual system-only installation uses `--phase system` as root, followed by `--phase user` as the normal user. `--serve` manages both phases itself and cannot be combined with `--phase`. The supplied system/binary recipes target Linux AMD64/ARM64; system groups use Ubuntu 24.04 packages.

## Components

| Namespace | Purpose |
| --- | --- |
| `pip.*` | Agent Python libraries, installed through uv |
| `npm.*` | npm tools using shared Node |
| `brew.*` | Formulae using persistent Homebrew |
| `apt.*` | System packages, optionally `apt.name=version` |
| `channels.*` | Channel dependencies in the service environment |
| `system.*` | Groups such as Office, LaTeX and fonts |
| `tools.*` | Official archives and special tools such as Chromium |
| `memory.*` | Optional embedding runtime and model assets |
| `presets.*` | Explicit combinations of components |

`npm.summarize` maps to `@steipete/summarize`. Unregistered pip/npm/brew/apt items use their shared backend after package-name validation. Unknown curated names and dependency cycles fail before installation. There is no `+full` selector.

`presets.rachebtms` retains the approved former full environment: document/scientific Python libraries and pytest; Node/npm/nvm; tea, gog, yq, summarize, mcporter and xurl; SSH/server utilities; C/C++ development tools; PDF/OCR/FFmpeg; LibreOffice Writer/Calc/Impress; scientific LaTeX/BibTeX/latexmk; Chinese fonts and Chromium/Playwright; Telegram dependencies; and BGE-small runtime/assets. Installation does not enable Telegram, embeddings or third-party accounts. Go, Bun, pipx, the standalone HF CLI, Manim and Azure/Bedrock/Olostep extras are not selected.

LibreOffice and LaTeX install only when selected directly or through a preset. APT resolves their shared system libraries. Venue-specific paper styles must accompany the paper. Playwright keeps its own unmodified driver and installs Chromium with the normal Headless Shell. Standard `chromium.launch(headless=True)` works; no runtime override or special channel is required.

## Additional optional packages

These components install into the same persistent Agent environment and use the shared install/import verification. Add them explicitly to the Compose command; they are not included in `+rachebtms` by default.

| Selector | Installed package / dependency handling |
| --- | --- |
| `+pip.httpx` | HTTPX library |
| `+pip.youtube-transcript-api` | `youtube-transcript-api`, import and CLI `youtube_transcript_api` |
| `+pip.marker-pdf` | `marker-pdf`, PyTorch and its declared dependencies; verifies `marker`, `torch` and the `marker` / `marker_single` entry points |
| `+pip.bs4` | Installs the actual `beautifulsoup4` distribution; verifies `bs4` |
| `+pip.markdown` | Python-Markdown library |
| `+pip.cairosvg` | CairoSVG plus shared Cairo / FFI / build prerequisites |
| `+apt.sshpass` / `+system.sshpass` | Ubuntu's `sshpass` package, included in `+all` through the shared APT backend |
| `+pip.manim` | Manim Community plus shared Cairo/Pango prerequisites, FFmpeg, fonts and the existing LaTeX suite with `dvisvgm` and `tipa` |

The underscore spellings `+pip.youtube_transcript_api` and `+pip.marker_pdf`, and `+pip.beautifulsoup4`, resolve to the same recipes and do not install twice. CairoSVG and Manim share their system prerequisites. Python package dependencies remain managed by uv. Each installation resolves all Python roots encountered so far in the same target environment, allowing uv to choose compatible versions when selected tools disagree about a shared dependency (for example Marker and Manim with Pillow). Service and Agent roots remain separate. See the upstream [CairoSVG requirements](https://cairosvg.org/documentation/) and [Manim installation guide](https://docs.manim.community/en/stable/installation/uv.html).

`marker-pdf` is a large optional installation because it depends on PyTorch. Setup installs the library and entry points without running OCR or downloading model weights. Actual conversions may require model downloads and, depending on the installed Marker version, an inference backend; see the [Marker installation and usage documentation](https://github.com/datalab-to/marker). GPU selection and credentials stay under the owner's control. Installation/import checks do not claim that a particular document or GPU workflow has been exercised.

## Recipes and execution

Each curated component is a module exporting `recipe`, with shared `depends(context)`, `verify(context)` and `install(context)` behavior. Presets only declare dependencies. The planner expands dependencies and deduplicates shared items. Package managers resolve their own package-level dependencies.

Installation is serial. Setup checks actual availability, installs missing dependencies, verifies results and records per-component progress in `state/tools/setup.json`. The receipts enable interrupted work to resume; they do not select components on later starts. Telegram setup shares the existing channel dependency tuple. Embedding setup reads the installed `cirno-memory` optional metadata rather than maintaining another list.

Root setup, service, Agent and development environments use ordinary uv virtual environments. Service and Agent package sets stay separate. Optional feature and CLI application installation reuse the uv command builder, through uv rather than falling back between installers. The Agent environment also includes a standard pip entry point for third-party Skills that invoke pip directly; its initial wheel comes from Python’s bundled offline seed. Existing Agent environments are refreshed with `--allow-existing` while preserving packages. Agent libraries and console scripts install directly into that virtual environment through uv. npm packages use the normal persistent global prefix. There is no separate Python target directory, `.pth` injection, Python command dispatcher, browser-driver deletion or executable stripping. System Python remains owned by the operating system.

## Persistence

All data uses the existing `~/.cirno` root:

- `state/tools/python`: Agent virtual environment.
- `state/tools/npm`: normal global npm prefix.
- `state/tools/nvm`: normal nvm tree and installed Node versions.
- `state/tools/bundled`: complete official archives such as Pandoc and xurl; Node is included in the base image.
- `state/tools/browsers`, `state/tools/models`: browser and embedding assets.
- `state/tools/homebrew`: Homebrew and formulae.
- `state/tools/apt`: verified package archives and user-added system-package receipts.
- `state/tools/uv/python`, `state/cli/cache/uv`: uv interpreter downloads and package cache.
- `state/cli`: CLI credentials, settings and caches.

The research Compose override uses the existing `state/tools/homebrew` subdirectory at Homebrew's fixed `/home/linuxbrew/.linuxbrew` prefix; there is one host data root to back up. A plain root mount uses a symlink, which may require source builds for some formulae.

Recreating a container reinstalls missing selected APT packages and previously user-added system packages, reusing archives. Indexes or missing archives may need network access. Setup-managed APT packages are tracked separately: removing a preset from Compose does not keep restoring its system packages as user additions. User-space tools reuse persistent files. Custom APT repositories and arbitrary `/etc` changes require a derived image or separate deployment configuration. Native binaries and compiled Python packages must match the CPU architecture. The service environment stays in the image; selected service extras are restored through uv after replacement.

The yt-dlp recipe installs its normal Python entry point and uses its standard user configuration to select the available Node runtime. Existing user configuration is preserved. Package libraries, launchers, browser drivers, browser variants and debug information are retained; dependency footprint reductions come from optional installation and reuse of ordinary caches.

### PyTorch accelerator selection

Setup defaults to `UV_TORCH_BACKEND=auto`: uv selects packages for the detected accelerator and uses CPU-only builds if none is available. This avoids installing CUDA-only dependencies on CPU-only or incompatible ARM64 hosts. Set `UV_TORCH_BACKEND` in Compose’s `environment` to choose a specific supported backend, such as `cpu` or `cu130`. Other packages retain their configured package indexes. See [uv’s PyTorch backend selection](https://docs.astral.sh/uv/guides/integration/pytorch/#automatic-backend-selection).
