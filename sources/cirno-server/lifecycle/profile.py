"""Data ownership and health identity for one gateway process."""

import hashlib
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import cirno_core as cirno
from cirno_server.lifecycle.runtime import ServerHealthIdentity


@contextmanager
def record_gateway_profile(
    instance, runtime, *, data_dir, workspace, port, verbose=False, cooperative_stop=False
):
    identity = ServerHealthIdentity(
        hashlib.sha256(str(instance.paths.state_path.resolve()).encode()).hexdigest(),
        uuid4().hex,
        cirno.__version__,
    )
    yield SimpleNamespace(health_identity=identity)
