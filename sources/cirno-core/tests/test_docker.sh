#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../.." || exit 1

RUN_ID="$$-${RANDOM}"
IMAGE_NAME="cirno-test-${RUN_ID}"
CONTAINER_NAME="cirno-test-run-${RUN_ID}"

cleanup() {
    result=$?
    trap - EXIT
    docker rm -f "$CONTAINER_NAME" > /dev/null 2>&1 || true
    docker rmi -f "$IMAGE_NAME" > /dev/null 2>&1 || true
    exit "$result"
}
trap cleanup EXIT

docker build -t "$IMAGE_NAME" .
docker run -d --name "$CONTAINER_NAME" -e CIRNO_DOCKER_BOOTSTRAP=1 "$IMAGE_NAME"
docker exec "$CONTAINER_NAME" /app/.venv/bin/python -c '
import json, time, urllib.request, urllib.error
for attempt in range(120):
    try:
        with urllib.request.urlopen("http://127.0.0.1:18790/v0/health", timeout=2) as response:
            if json.load(response).get("ready"):
                break
    except (urllib.error.URLError, TimeoutError):
        pass
    time.sleep(.5)
else:
    raise SystemExit("Cirno did not become ready")
'
docker cp sources/development/verify_setup_image.py "$CONTAINER_NAME:/tmp/verify_setup_image.py"
docker cp sources/development/verify_setup_minimal.py "$CONTAINER_NAME:/tmp/verify_setup_minimal.py"
docker exec --user 1000:1000 "$CONTAINER_NAME" /app/.venv/bin/python /tmp/verify_setup_image.py --base
docker exec --user 1000:1000 "$CONTAINER_NAME" /app/.venv/bin/python /tmp/verify_setup_minimal.py
docker cp sources/development/verify_setup_toolchains.py "$CONTAINER_NAME:/tmp/verify_setup_toolchains.py"
docker exec --user 1000:1000 "$CONTAINER_NAME" /app/.venv/bin/python /tmp/verify_setup_toolchains.py
echo "=== All checks passed ==="
