"""Saved policies across CLI, connection supervision, and TUI launch/disconnect."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import toml

from openconnect_saml import app, config, sessions
from openconnect_saml.cli import _handle_disconnect_command


def configured():
    return config.Config.from_dict(
        {
            "username_only": True,
            "preserve_session": True,
            "preserve_session_on_interrupt": True,
            "chrome_channel": "chrome",
            "profiles": {
                "usc": {
                    "server": "https://vpn.usc.edu",
                    "browser": "chrome",
                    "openconnect_args": ["--script", "/opt/homebrew/bin/vpn-slice 10.137.0.0/16"],
                }
            },
        }
    )


def test_saved_policy_roundtrip_and_explicit_false_overrides():
    cfg = configured()
    cfg.get_profile("usc").preserve_session = False
    cfg.get_profile("usc").preserve_session_on_interrupt = False
    cfg.get_profile("usc").username_only = False
    restored = config.Config.from_dict(toml.loads(toml.dumps(cfg.as_dict())))
    for field in ("preserve_session", "preserve_session_on_interrupt", "username_only"):
        assert restored.get_setting(field) is True
        assert restored.get_setting(field, "usc") is False
    assert restored.chrome_channel == "chrome"
    assert restored.get_profile("usc").openconnect_args == cfg.get_profile("usc").openconnect_args


def test_example_configuration_loads():
    example = Path(__file__).parents[1] / "examples" / "usc-manual.toml"
    cfg = config.Config.from_dict(toml.load(example))
    assert cfg.get_setting("preserve_session_on_interrupt", "usc") is True
    assert cfg.get_setting("username_only", "usc") is True
    assert cfg.get_profile("usc").credentials.username == "YOUR_USC_NETID"


@pytest.mark.skipif(__import__("os").name != "posix", reason="Preserving sessions uses SIGHUP")
@pytest.mark.parametrize("cli_override, expected", [(None, True), (False, False), (True, True)])
def test_disconnect_honors_connection_policy_even_without_original_config(cli_override, expected):
    # This connection was launched with a different --config file. Its policy
    # travels in non-secret session metadata, not in the current default config.
    active = sessions.Session(profile="usc", server="vpn.usc.edu", pid=999, preserve_session=True)
    options = SimpleNamespace(profile_name="usc", all=False, preserve_session=cli_override)
    with (
        patch("openconnect_saml.cli.config.load", return_value=config.Config()),
        patch("openconnect_saml.sessions.load", return_value=active),
        patch("openconnect_saml.sessions.kill", return_value=True) as stop,
    ):
        assert _handle_disconnect_command(options) == 0
    stop.assert_called_once_with("usc", **({"preserve_session": True} if expected else {}))


@pytest.mark.parametrize("interrupt_override", [None, False])
def test_connection_resolves_saved_arguments_and_records_disconnect_policy(
    tmp_path, monkeypatch, interrupt_override
):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    cfg = configured()
    options = SimpleNamespace(
        profile_name="usc",
        proxy=None,
        ac_version="version",
        openconnect_args=[],
        user=None,
        preserve_session_on_interrupt=interrupt_override,
    )
    host = config.HostProfile("vpn.usc.edu", "", "")
    with patch("openconnect_saml.app.run_openconnect", return_value=0) as run:
        assert app._connect_with_token_refresh(options, cfg, MagicMock(), host) == 0
    assert run.call_args.args[4] == cfg.get_profile("usc").openconnect_args
    assert run.call_args.kwargs["preserve_session_on_interrupt"] is (
        interrupt_override is not False
    )
    run.call_args.kwargs["on_pid"](1234)
    recorded = sessions.Session.from_dict(
        __import__("json").loads(sessions.session_file("usc").read_text())
    )
    assert recorded.preserve_session is True
    assert recorded.pid == 1234
    # Explicit CLI OpenConnect arguments replace the saved list.
    options.openconnect_args = ["--script", "other-script"]
    with patch("openconnect_saml.app.run_openconnect", return_value=0) as run:
        app._connect_with_token_refresh(options, cfg, MagicMock(), host)
    assert run.call_args.args[4] == ["--script", "other-script"]


def test_saved_username_and_system_chrome_need_no_repeated_flags():
    cfg = configured()
    cfg.credentials = config.Credentials("remembered-netid")
    options = SimpleNamespace(
        profile_name="usc",
        user=None,
        server="vpn.usc.edu",
        use_profile_selector=False,
        usergroup="",
        authgroup="",
        profile_path=None,
        browser=None,
        browser_display_mode="shown",
        proxy=None,
        ac_version="version",
        on_disconnect="",
        no_token_cache=True,
    )
    with (
        patch.object(app, "authenticate_to", AsyncMock()) as auth,
        patch.object(app, "_read_password") as prompt,
    ):
        asyncio.run(app._run(options, cfg))
    prompt.assert_not_called()
    assert auth.call_args.args[2].username == "remembered-netid"
    assert auth.call_args.args[2].username_only is True
    assert auth.call_args.kwargs["chrome_channel"] == "chrome"


def test_tui_disconnects_managed_profile_instead_of_terminating_supervisor():
    from openconnect_saml.interactive_tui import InteractiveTUI

    cfg = configured()
    cfg.add_profile("zzz", {"server": "other.invalid"})
    with patch("openconnect_saml.interactive_tui.config.load", return_value=cfg):
        tui = InteractiveTUI()
    child = MagicMock()
    child.poll.return_value = None
    with patch("openconnect_saml.interactive_tui.subprocess.Popen", return_value=child):
        tui._connect()
    tui.cursor = 1
    with patch(
        "openconnect_saml.interactive_tui.subprocess.run",
        return_value=SimpleNamespace(returncode=0),
    ) as stop:
        tui._disconnect()
    assert stop.call_args.args[0][-2:] == ["disconnect", "usc"]
    child.terminate.assert_not_called()
