"""Wait for readiness, stopping immediately if startup has already failed."""

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument("--timeout", type=int, required=True)
parser.add_argument("--name", default="cirno-smoke")
parser.add_argument("--url", default="http://127.0.0.1:18790/v0/health")
arguments = parser.parse_args()
deadline = time.monotonic() + arguments.timeout
while time.monotonic() < deadline:
    state = subprocess.check_output(["docker", "inspect", "--format", "{{.State.Status}}", arguments.name], text=True).strip()
    if state != "running":
        subprocess.run(["docker", "logs", arguments.name], check=True)
        raise SystemExit(f"Container stopped during initialization: {state}")
    try:
        with urllib.request.urlopen(arguments.url, timeout=5) as response:
            if json.load(response).get("ready"):
                break
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        pass
    time.sleep(2)
else:
    subprocess.run(["docker", "logs", arguments.name], check=True)
    raise SystemExit(f"Container was not ready after {arguments.timeout} seconds")
