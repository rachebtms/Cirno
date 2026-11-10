#!/bin/bash
set -euo pipefail
# Run as the non-root cirno user, before application installation.
brew bundle install --no-upgrade --file=/tmp/full-image.Brewfile
npm install --global --prefix /opt/cirno/node-tools mcporter@0.16.1
python3.12 /tmp/bundle_embedding.py /opt/cirno/models/bge-small-zh-v1.5
brew cleanup --prune=all --scrub
rm -rf "$HOME/.cache/uv" "$HOME/.npm"
