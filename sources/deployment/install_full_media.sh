#!/bin/bash
set -euo pipefail
# The full-only rendering layer uses the Homebrew Python without altering it.
apt-get update
apt-get install -y --no-install-recommends \
    pkg-config libcairo2-dev libpango1.0-dev \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    fontconfig fonts-noto-cjk fonts-dejavu-core \
    texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
    texlive-science latexmk
uv pip install --python python3.12 --target /opt/cirno/python-packages \
    --no-cache --requirement /tmp/full-image-python.txt
PYTHONPATH=/opt/cirno/python-packages python3.12 -m playwright install --with-deps chromium
fc-cache -f
chown -R cirno:cirno /opt/cirno/python-packages /opt/cirno/browsers
rm -rf /var/lib/apt/lists/*
