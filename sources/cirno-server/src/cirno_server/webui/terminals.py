"""Owner-operated PTY terminals with bounded replay, local or over OpenSSH."""

from __future__ import annotations

import asyncio
import codecs
import errno
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from cirno_core.nodes.service import Nodes


@dataclass
class TerminalSession:
    process: asyncio.subprocess.Process
    master: int
    label: str
    output: str = ""
    offset: int = 0
    decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")("replace")
    )
    eof: bool = False
    error: str | None = None


class Terminals:
    def __init__(self):
        self.sessions: dict[str, TerminalSession] = {}
        self._creation_lock = asyncio.Lock()

    async def create(
        self,
        *,
        cwd: str,
        node_id: str | None = None,
        cols: int = 100,
        rows: int = 30,
        key: str | None = None,
    ) -> dict:
        identifier = str(UUID(key)) if key is not None else uuid4().hex
        # A browser tab keeps its identity across reloads. Serialize admission so
        # retrying the same connection cannot leave a second, unreachable shell.
        async with self._creation_lock:
            existing = self.sessions.get(identifier)
            if existing is not None:
                return {"id": identifier, "label": existing.label}
            if len(self.sessions) >= 12:
                raise ValueError("Close a terminal before opening another (12 terminal limit)")
            return await self._create(
                cwd=cwd,
                node_id=node_id,
                cols=cols,
                rows=rows,
                identifier=identifier,
            )

    async def _create(
        self,
        *,
        cwd: str,
        node_id: str | None = None,
        cols: int = 100,
        rows: int = 30,
        identifier: str,
    ) -> dict:
        if os.name != "posix":
            raise ValueError("Interactive server terminals require Linux or macOS")
        if len(self.sessions) >= 12:
            raise ValueError("Close a terminal before opening another (12 terminal limit)")
        import pty
        import shlex

        args = [os.environ.get("SHELL") or "/bin/sh", "-l"]
        env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        label = "Local"
        if node_id:
            nodes = Nodes()
            node = await asyncio.to_thread(nodes.node, node_id)
            args = [
                *(await asyncio.to_thread(nodes.arguments, node)),
                "-tt",
                f"{node.username}@{node.host}",
                f'cd {shlex.quote(node.working_directory)} && exec "${{SHELL:-/bin/sh}}" -l',
            ]
            env.update(
                await asyncio.to_thread(nodes.environment, node.password if node.auth_method == "password" else None) or {}
            )
            label = node.name
        cols, rows = max(2, min(500, int(cols))), max(2, min(200, int(rows)))
        directory = str(Path(cwd).expanduser().resolve(strict=True))
        master, slave = pty.openpty()
        # The helper acquires its own controlling TTY after setsid, then execs
        # the shell. No preexec_fn runs in this multithreaded server.
        helper = "import os,sys,fcntl,termios;fcntl.ioctl(0,termios.TIOCSCTTY,0);os.execvpe(sys.argv[1],sys.argv[1:],os.environ)"
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                helper,
                *args,
                stdin=slave,
                stdout=slave,
                stderr=slave,
                cwd=directory,
                env=env,
                start_new_session=True,
                close_fds=True,
            )
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        os.set_blocking(master, False)
        session = TerminalSession(process, master, label)
        self.sessions[identifier] = session
        loop = asyncio.get_running_loop()

        def read():
            try:
                data = os.read(master, 65536)
            except BlockingIOError:
                return
            except OSError as error:
                if error.errno != errno.EIO:
                    loop.remove_reader(master)
                    session.error = str(error)
                    return
                data = b""
            if not data:
                loop.remove_reader(master)
                session.eof = True
                return
            session.output += session.decoder.decode(data)
            excess = len(session.output) - 128_000
            if excess > 0:
                session.output = session.output[excess:]
                session.offset += excess

        loop.add_reader(master, read)

        self.resize(identifier, cols, rows)
        return {"id": identifier, "label": label}

    def get(self, identifier: str) -> TerminalSession:
        if identifier not in self.sessions:
            raise KeyError("Terminal no longer exists; open a new terminal")
        return self.sessions[identifier]

    def read(self, identifier: str, cursor: int = 0) -> dict:
        session = self.get(identifier)
        if session.error:
            raise RuntimeError(session.error)
        cursor = max(0, cursor)
        return {
            "data": session.output[max(0, cursor - session.offset) :],
            "cursor": session.offset + len(session.output),
            "reset": cursor < session.offset,
            "exit_code": session.process.returncode if session.eof else None,
        }

    async def write(self, identifier: str, data: str) -> dict:
        if not isinstance(data, str) or len(data.encode()) > 65536:
            raise ValueError("Terminal input exceeds 64 KiB")
        session = self.get(identifier)
        pending = memoryview(data.encode())
        loop = asyncio.get_running_loop()
        while pending:
            if self.sessions.get(identifier) is not session:
                raise KeyError("Terminal was closed")
            try:
                count = os.write(session.master, pending)
                pending = pending[count:]
            except BlockingIOError:
                ready = loop.create_future()

                def writable():
                    if not ready.done():
                        ready.set_result(None)

                loop.add_writer(session.master, writable)
                try:
                    async with asyncio.timeout(5):
                        await ready
                finally:
                    loop.remove_writer(session.master)
        return {"ok": True}

    def resize(self, identifier: str, cols: int, rows: int) -> dict:
        import fcntl
        import struct
        import termios

        session = self.get(identifier)
        cols, rows = max(2, min(500, int(cols))), max(2, min(200, int(rows)))
        fcntl.ioctl(session.master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
        return {"ok": True}

    async def close(self, identifier: str) -> dict:
        # Closing a tab while its shell is still starting must wait for that
        # admission, rather than leaving a newly spawned shell without a tab.
        async with self._creation_lock:
            return await self._close(identifier)

    async def _close(self, identifier: str) -> dict:
        session = self.sessions.pop(identifier, None)
        if session is None:
            return {"ok": True}
        asyncio.get_running_loop().remove_reader(session.master)
        if session.process.returncode is None:
            try:
                os.killpg(session.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        os.close(session.master)
        await session.process.wait()
        return {"ok": True}

    async def close_all(self):
        for identifier in list(self.sessions):
            await self.close(identifier)
