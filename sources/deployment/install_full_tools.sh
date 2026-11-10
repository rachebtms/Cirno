#!/bin/bash
set -euo pipefail
# Run as the non-root cirno user, before application installation.
brew bundle install --no-upgrade --file=/tmp/full-image.Brewfile
npm install --global --prefix /opt/cirno/node-tools mcporter@0.16.1
GOBIN=/opt/cirno/bin go install github.com/xdevplatform/xurl@v1.3.4
UV_TOOL_DIR=/opt/cirno/python-tools UV_TOOL_BIN_DIR=/opt/cirno/bin \
    uv tool install --python 3.12 'huggingface-hub>=1,<2'
python3.12 /tmp/bundle_embedding.py /opt/cirno/models/bge-small-zh-v1.5
brew cleanup --prune=all --scrub
go clean -modcache -cache
rm -rf "$HOME/.cache/uv" "$HOME/.npm"
