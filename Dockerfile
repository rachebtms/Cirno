FROM node:24-bookworm-slim AS webui-builder

WORKDIR /app/sources/cirno-web
COPY sources/cirno-web/package.json sources/cirno-web/package-lock.json ./
RUN npm ci
COPY sources/cirno-web/ ./
COPY sources/cirno-core/agent/tools/names.json /app/sources/cirno-core/agent/tools/names.json
RUN npm run build

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git bubblewrap openssh-client libmagic1 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep the runtime environment writable by the non-root cirno user. Enabled
# channels may install their manifest-declared dependencies at startup.
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
RUN uv venv --seed "$VIRTUAL_ENV"

# Install Python dependencies without building the project (cached layer).
# Source and documentation changes only invalidate the final package install.
ARG CIRNO_EXTRAS=
COPY pyproject.toml ./
RUN set -- && \
    for extra in $(printf '%s' "$CIRNO_EXTRAS" | tr ',' ' '); do \
        set -- "$@" --extra "$extra"; \
    done && \
    uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache -r pyproject.toml "$@"

# Copy the full source and install
COPY README.md LICENSE THIRD_PARTY_NOTICES.md hatch_build.py ./
COPY documents/ documents/
COPY sources/cirno-core/ sources/cirno-core/
COPY sources/deployment/install_channel_dependencies.py scripts/
COPY --from=webui-builder /app/build/webui/ build/webui/
RUN CIRNO_SKIP_WEBUI_BUILD=1 uv pip install --python "$VIRTUAL_ENV/bin/python" --no-cache --no-deps .

# Preinstall selected channel dependencies from their manifests. A comma-separated
# list selects dependencies for the included channels.
ARG CIRNO_CHANNELS=
RUN for channel in $(printf '%s' "$CIRNO_CHANNELS" | tr ',' ' '); do \
        python -m scripts.install_channel_dependencies "$channel"; \
    done


# Create the non-root user and hand ownership of the writable virtualenv to it.
RUN useradd -m -u 1000 -s /bin/bash cirno && \
    mkdir -p /home/cirno/.cirno && \
    chown -R cirno:cirno /home/cirno /app/.venv

COPY sources/deployment/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Start as root so the entrypoint can chown a mounted data directory
# before dropping to the non-root
# cirno user via setpriv. The entrypoint drops privileges on every root start
# and fails closed if it cannot, so the agent never runs as root (see
# entrypoint.sh).
USER root
ENV HOME=/home/cirno
# Include Python crash diagnostics in container logs.
ENV PYTHONUNBUFFERED=1 PYTHONFAULTHANDLER=1

# Gateway health endpoint and optional WebUI/WebSocket channel ports
EXPOSE 18790 8765

ENTRYPOINT ["entrypoint.sh"]
CMD ["status"]
