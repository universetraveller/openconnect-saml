"""Foreground OpenConnect supervision with deliberate Ctrl-C preservation."""

import contextlib
import signal
import subprocess
import sys

import structlog

logger = structlog.get_logger()
_HAS_PROCESS_GROUP = sys.version_info >= (3, 11)


def run_preserving_interrupt(command, cookie, *, on_pid=None, on_connect=None):
    """Keep the child out of the terminal's SIGINT group; send SIGHUP instead.

    The caller authenticates sudo in the foreground first. Keeping the same
    session/controlling terminal allows sudo to reuse its per-terminal ticket.
    """
    proc = None
    interrupted = False

    def interrupt(_signum, _frame):
        nonlocal interrupted
        interrupted = True
        if proc is not None:
            with contextlib.suppress(ProcessLookupError):
                proc.send_signal(signal.SIGHUP)

    options = {"stdin": subprocess.PIPE}
    if _HAS_PROCESS_GROUP:
        options["process_group"] = 0
    else:
        # Python 3.10 has no Popen(process_group=...). Start a fresh isolated
        # interpreter to set the group before exec; avoid preexec_fn in a
        # potentially multithreaded application. This bootstrap runs before
        # any sudo privilege elevation.
        command = [
            sys.executable,
            "-I",
            "-c",
            "import os, sys; os.setpgid(0, 0); os.execvp(sys.argv[1], sys.argv[1:])",
            *command,
        ]

    previous = signal.signal(signal.SIGINT, interrupt)
    try:
        proc = subprocess.Popen(command, **options)  # nosec
        if interrupted:
            interrupt(signal.SIGINT, None)
        try:
            proc.stdin.write(cookie)
            proc.stdin.close()
        except BrokenPipeError:
            pass
        if on_pid:
            try:
                on_pid(proc.pid)
            except Exception as exc:
                logger.warning("on_pid callback raised", error=str(exc))
        if on_connect and not interrupted:
            on_connect()
        rc = proc.wait()
        return 0 if interrupted else rc
    finally:
        signal.signal(signal.SIGINT, previous)
