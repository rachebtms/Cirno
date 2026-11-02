"""Embedded web UI assets.

The ``dist/`` subdirectory holds the production WebUI bundle served by the
gateway. It is shipped inside the published wheel and is rebuilt automatically
by the ``webui-build`` Hatch hook during ``python -m build``. In an editable
source checkout, ``cirno webui`` and ``cirno gateway`` detect stale local
frontend sources and can rebuild the bundle before serving it. WebUI developers
can still use the Vite dev server at ``npm --prefix sources/cirno-web run dev``.
"""
