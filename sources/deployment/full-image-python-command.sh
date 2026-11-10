#!/bin/sh
set -eu
tool=$(basename "$0")
case "$tool" in
    playwright)
        exec "$CIRNO_SHELL_VENV/bin/python" -m "$tool" "$@"
        ;;
    chromium)
        exec "$CIRNO_SHELL_VENV/bin/python" -c '
import os
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as browser:
    executable = browser.chromium.executable_path
os.execv(executable, [executable, *sys.argv[1:]])
' "$@"
        ;;
    *)
        echo "Unsupported Python tool: $tool" >&2
        exit 2
        ;;
esac
