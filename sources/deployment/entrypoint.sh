#!/bin/sh
# Root setup uses its own immutable uv environment and isolated Python.
exec /opt/cirno/setup/bin/python -I -m cirno_setup "$@"
