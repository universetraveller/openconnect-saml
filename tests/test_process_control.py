"""Real subprocess signal delivery; no VPN, sudo privileges, or live credentials."""

import contextlib
import json
import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX process groups and SIGHUP")


@pytest.mark.parametrize(
    "preserve, use_sudo, legacy_group",
    [(False, False, False), (True, False, False), (True, True, False), (True, True, True)],
)
def test_terminal_group_ctrl_c_is_translated_only_when_configured(
    tmp_path, preserve, use_sudo, legacy_group
):
    fake_client = tmp_path / "openconnect"
    fake_client.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent("""\
        import json, os, signal, sys, time
        from pathlib import Path
        result = Path(os.environ["OC_TEST_RESULT"])
        def stop(sig, frame):
            result.write_text(signal.Signals(sig).name)
            sys.exit(0)
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGHUP, stop)
        cookie = sys.stdin.read()
        Path(os.environ["OC_TEST_READY"]).write_text(json.dumps({
            "pid": os.getpid(), "group": os.getpgrp(), "cookie": cookie
        }))
        while True:
            time.sleep(1)
    """)
    )
    fake_client.chmod(0o700)
    fake_sudo = tmp_path / "sudo"
    fake_sudo.write_text(
        f"#!{sys.executable}\n"
        + textwrap.dedent("""\
        import os, sys
        from pathlib import Path
        if sys.argv[1:] == ["-v"]:
            Path(os.environ["OC_TEST_SUDO_AUTH"]).write_text("validated")
            sys.exit(0)
        assert sys.argv[1] == "-n"
        os.execvp(sys.argv[2], sys.argv[2:])
    """)
    )
    fake_sudo.chmod(0o700)
    parent_program = textwrap.dedent("""\
        import os
        from types import SimpleNamespace
        from openconnect_saml.app import run_openconnect
        from openconnect_saml.config import HostProfile
        import openconnect_saml.process_control as process_control
        if os.environ["OC_TEST_LEGACY_GROUP"] == "1":
            process_control._HAS_PROCESS_GROUP = False
        try:
            rc = run_openconnect(
                SimpleNamespace(session_token="test-cookie", server_cert_hash="pin"),
                HostProfile("vpn.invalid", "", ""), None, "version", [],
                no_sudo=os.environ["OC_TEST_SUDO"] != "1",
                preserve_session_on_interrupt=os.environ["OC_TEST_PRESERVE"] == "1",
            )
        except KeyboardInterrupt:
            rc = 0
        raise SystemExit(rc)
    """)
    ready, result, sudo_auth = (tmp_path / n for n in ("ready", "result", "sudo-auth"))
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "OC_TEST_READY": str(ready),
        "OC_TEST_RESULT": str(result),
        "OC_TEST_SUDO_AUTH": str(sudo_auth),
        "OC_TEST_SUDO": "1" if use_sudo else "0",
        "OC_TEST_PRESERVE": "1" if preserve else "0",
        "OC_TEST_LEGACY_GROUP": "1" if legacy_group else "0",
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", parent_program],
        env=env,
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    child = None
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists(), proc.communicate(timeout=2)
        child = json.loads(ready.read_text())
        assert child["cookie"] == "test-cookie"
        assert (child["group"] != proc.pid) is preserve
        # A terminal delivers Ctrl-C to the entire foreground process group.
        os.killpg(proc.pid, signal.SIGINT)
        stdout, stderr = proc.communicate(timeout=10)
        assert proc.returncode == 0, (stdout, stderr)
        assert result.read_text() == ("SIGHUP" if preserve else "SIGINT")
        assert sudo_auth.exists() is use_sudo
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)
        if child:
            with contextlib.suppress(ProcessLookupError):
                os.kill(child["pid"], signal.SIGKILL)
