# The browser bundle is architecture-independent; never run Node under QEMU.
FROM --platform=$BUILDPLATFORM node:24-bookworm-slim AS webui-builder

WORKDIR /app/sources/cirno-web
COPY sources/cirno-web/package.json sources/cirno-web/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --prefer-offline
COPY sources/cirno-web/ ./
COPY sources/cirno-core/src/cirno_core/agent/tools/names.json /app/sources/cirno-core/src/cirno_core/agent/tools/names.json
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS python-build-tools

# One base for every deployment. Optional tools are selected through cirno-setup.
FROM ubuntu:24.04 AS runtime
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git bubblewrap openssh-client libmagic1 libatomic1 util-linux \
    python3.12 python3.12-venv && rm -rf /var/lib/apt/lists/* && \
    userdel ubuntu && useradd -m -u 1000 -s /bin/bash cirno && \
    mkdir -p /home/linuxbrew/.linuxbrew /opt/cirno/bin /opt/cirno/setup && \
    chown -R cirno:cirno /home/linuxbrew && \
    ln -s /usr/bin/fdfind /opt/cirno/bin/fd && \
    ln -s /usr/bin/batcat /opt/cirno/bin/bat && \
    ln -s /usr/bin/python3.12 /opt/cirno/bin/python
COPY --from=python-build-tools /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/
# Keep the official Node/npm layout for npx-based MCP servers and CLI installers.
COPY --from=webui-builder /usr/local/bin/node /usr/local/bin/node
COPY --from=webui-builder /usr/local/LICENSE /usr/share/licenses/nodejs/LICENSE
COPY --from=webui-builder /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && \
    ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
ENV HOME=/home/cirno \
    HOMEBREW_PREFIX=/home/linuxbrew/.linuxbrew \
    HOMEBREW_NO_ANALYTICS=1 HOMEBREW_NO_AUTO_UPDATE=1 \
    HOMEBREW_CACHE=/home/cirno/.cirno/state/cli/cache/homebrew \
    PLAYWRIGHT_BROWSERS_PATH=/home/cirno/.cirno/state/tools/browsers \
    PATH="/usr/local/bin:/opt/cirno/bin:/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:$PATH"
COPY sources/deployment/tools-shell.sh /etc/profile.d/cirno-tools.sh
ENV CIRNO_SHELL_VENV=/home/cirno/.cirno/state/tools/python \
    TEA_CONFIG_DIR=/home/cirno/.cirno/state/cli/config/tea \
    PIP_CACHE_DIR=/home/cirno/.cirno/state/cli/cache/pip \
    NPM_CONFIG_CACHE=/home/cirno/.cirno/state/cli/cache/npm \
    NPM_CONFIG_USERCONFIG=/home/cirno/.cirno/state/cli/config/npmrc \
    BASH_ENV=/etc/profile.d/cirno-tools.sh \
    CIRNO_BUNDLED_EMBEDDING_DIR=/home/cirno/.cirno/state/tools/models/bge-small-zh-v1.5 \
    XDG_CONFIG_HOME=/home/cirno/.cirno/state/cli/config \
    XDG_DATA_HOME=/home/cirno/.cirno/state/cli/data \
    XDG_CACHE_HOME=/home/cirno/.cirno/state/cli/cache \
    HF_HOME=/home/cirno/.cirno/state/cli/huggingface \
    GOPATH=/home/cirno/.cirno/state/tools/go \
    GOBIN=/home/cirno/.cirno/state/tools/bin \
    BUN_INSTALL=/home/cirno/.cirno/state/tools/bun \
    GH_CONFIG_DIR=/home/cirno/.cirno/state/cli/config/gh \
    GIT_CONFIG_GLOBAL=/home/cirno/.cirno/state/cli/gitconfig \
    NPM_CONFIG_PREFIX=/home/cirno/.cirno/state/tools/npm \
    UV_TOOL_DIR=/home/cirno/.cirno/state/tools/uv \
    UV_CACHE_DIR=/home/cirno/.cirno/state/cli/cache/uv \
    UV_PYTHON_INSTALL_DIR=/home/cirno/.cirno/state/tools/uv/python \
    UV_TOOL_BIN_DIR=/home/cirno/.cirno/state/tools/bin \
    PIPX_HOME=/home/cirno/.cirno/state/tools/pipx \
    PIPX_BIN_DIR=/home/cirno/.cirno/state/tools/bin \
    NVM_DIR=/home/cirno/.cirno/state/tools/nvm \
    PATH="/home/cirno/.cirno/state/tools/bin:/home/cirno/.cirno/state/tools/npm/bin:/home/cirno/.cirno/state/tools/bun/bin:/home/cirno/.cirno/state/tools/bundled/pandoc/bin:/home/cirno/.cirno/state/tools/bundled/xurl/bin:$PATH" \
    CIRNO_SERVICE_PYTHON=/app/.venv/bin/python

WORKDIR /app

# Keep the runtime environment writable by the non-root cirno user. Enabled
# channels may install their manifest-declared dependencies at startup.
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="$CIRNO_SHELL_VENV/bin:/app/.venv/bin:$PATH"

# Build the local distributions together; none is fetched from PyPI.
ARG CIRNO_EXTRAS=
ARG CIRNO_CHANNELS=
COPY pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
COPY documents/ documents/
COPY sources/cirno/ sources/cirno/
COPY sources/cirno-setup/ sources/cirno-setup/
COPY sources/cirno-memory/ sources/cirno-memory/
COPY sources/cirno-usage/ sources/cirno-usage/
COPY sources/cirno-vault/ sources/cirno-vault/
COPY sources/cirno-core/ sources/cirno-core/
COPY sources/cirno-server/ sources/cirno-server/
COPY sources/deployment/install_channel_dependencies.py scripts/
COPY --from=webui-builder /app/build/webui/ build/webui/
# Install and hand ownership over in one layer. A later recursive chown would
# copy the installed environment into a second image layer.
RUN uv venv --python /usr/bin/python3.12 "$VIRTUAL_ENV" && \
    extras="${CIRNO_EXTRAS:-${CIRNO_EXTRAS_DEFAULT:-}}" && \
    if [ -n "$extras" ]; then project=".[$extras]"; else project="."; fi && \
    CIRNO_SKIP_WEBUI_BUILD=1 uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache \
    ./sources/cirno-setup ./sources/cirno-memory ./sources/cirno-usage ./sources/cirno-vault ./sources/cirno-core ./sources/cirno-server "$project" && \
    for channel in $(printf '%s' "${CIRNO_CHANNELS:-${CIRNO_CHANNELS_DEFAULT:-}}" | tr ',' ' '); do \
        python -m scripts.install_channel_dependencies "$channel" || exit $?; \
    done && \
    uv venv --python /usr/bin/python3.12 /opt/cirno/setup && \
    uv pip install --python /opt/cirno/setup/bin/python --no-cache ./sources/cirno-setup && \
    /opt/cirno/setup/bin/python -I -m cirno_setup --snapshot-base /opt/cirno/setup/lib/python3.12/site-packages/cirno_setup/assets/base-apt-packages.json && \
    printf '%s\n' 'DPkg::Post-Invoke { "HOME=/home/cirno /opt/cirno/setup/bin/python -I -m cirno_setup --record-apt"; };' > /etc/apt/apt.conf.d/99cirno-persistence && \
    mkdir -p /home/cirno/.cirno && \
    chown -R cirno:cirno /home/cirno /app/.venv

COPY sources/deployment/entrypoint.sh /opt/cirno/bin/cirno-setup
RUN chmod +x /opt/cirno/bin/cirno-setup

# Start as root so the entrypoint can chown a mounted data directory
# before dropping to the non-root
# cirno user via setpriv. The entrypoint drops privileges on every root start
# and fails closed if it cannot, so the agent never runs as root (see
# entrypoint.sh).
USER root
ENV HOME=/home/cirno
# Include Python crash diagnostics in container logs.
ENV PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1
ENV VIRTUAL_ENV=$CIRNO_SHELL_VENV
ENV PATH="$CIRNO_SHELL_VENV/bin:$PATH"

# Service health endpoint and Web UI/WebSocket port
EXPOSE 18790 8765

ENTRYPOINT ["/opt/cirno/bin/cirno-setup", "--serve"]
CMD []
