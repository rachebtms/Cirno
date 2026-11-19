#!/usr/bin/env bash
# GitHub-hosted Ubuntu runners only; never part of container startup.
set -euo pipefail

interface=$(ip -o -4 route show to default | awk 'NR == 1 { print $5 }')
sudo resolvectl dns "$interface" 1.1.1.1 1.0.0.1
sudo resolvectl flush-caches

# Regional EC2 mirrors can stall browser dependency preparation for most of a job.
sudo python3 - <<'PY'
import re
from pathlib import Path

sources = Path('/etc/apt/sources.list.d')
for path in [Path('/etc/apt/sources.list'), *sources.glob('*.sources'), *sources.glob('*.list')]:
    if not path.is_file():
        continue
    previous = path.read_text()
    updated = re.sub(
        r'https?://(?:[a-z0-9-]+\.)*ec2\.archive\.ubuntu\.com/ubuntu/?',
        'https://archive.ubuntu.com/ubuntu/', previous,
    )
    updated = re.sub(r'http://((?:archive|security|ports)\.ubuntu\.com/)', r'https://\1', updated)
    if previous != updated:
        path.write_text(updated)
        print(f'Using the Ubuntu archive in {path}')
PY

getent ahostsv4 archive.ubuntu.com
getent ahostsv4 ports.ubuntu.com
