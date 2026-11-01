"""Data ownership and health identity for one gateway process."""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import cirno
from cirno.gateway.runtime import GatewayHealthIdentity


@contextmanager
def record_gateway_profile(
    instance, runtime, *, data_dir, workspace, port, verbose=False, cooperative_stop=False
):
    identity = GatewayHealthIdentity(
        hashlib.sha256(str(instance.paths.state_path.resolve()).encode()).hexdigest(),
        uuid4().hex,
        cirno.__version__,
    )
    yield SimpleNamespace(health_identity=identity)
