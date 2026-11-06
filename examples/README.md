# USC setup

This adaptation lives on **`feat/usc-vpn-adaptation`**, separately from `main`.
It includes the supporting authentication, browser, configuration, and process
supervision changes as well as the USC examples. Use this branch's editable
installation so the launcher runs the modified code:

```bash
git switch feat/usc-vpn-adaptation
# If .venv does not exist yet, create it with: uv venv .venv
uv pip install --python .venv/bin/python -e '.[chrome,tui]'
```

The published v0.25.0 package does not contain this adaptation. The launcher
explicitly selects `.venv/bin/openconnect-saml` from this checkout instead of
whichever version is installed globally.

## Changes in this branch

- Store VPN session cookies, gateway URLs, and certificate pins together in the
  OS keyring. Try a saved cookie first and refresh SSO once if it is rejected.
- Reuse a dedicated Chrome profile for SSO/Duo cookies and installed extensions,
  including the iCloud Passwords setup described in the browser guide.
- Save the username, username-only login mode, Chrome channel/profile, and
  disconnect policies in config. No repeated `--user` or preservation flags
  are needed after configuration.
- Support `preserve_session_on_interrupt = true`: Ctrl-C sends SIGHUP and waits
  for tunnel cleanup without logging the server session out. The default
  remains ordinary logout. `disconnect --logout` explicitly overrides a saved
  preservation policy.
- Keep `vpn-slice 10.137.0.0/16` in the launcher and saved profile arguments, so
  CLI and TUI use the same USC split-routing policy.
- Make Qt username-only autofill leave manually entered fields and form
  submission alone. Make TUI disconnect the recorded VPN process using the
  connection's saved policy.

## Configure and connect

`connect_usc.sh` is a suggested replacement for the logic in `../connect_vpn.sh`.
It uses this checkout's `.venv/bin/openconnect-saml`, keeps the original
`10.137.0.0/16` vpn-slice routing, and refreshes sudo credentials before login.
It accepts connection flags, for example `--browser qt`.

1. Merge `usc-manual.toml` into `~/.config/openconnect-saml/usc-manual.toml`.
   Keep top-level keys before any `[table]` headers. Preserve unrelated existing
   settings, replace `YOUR_USC_NETID`, and verify the path using `command -v vpn-slice`.
2. Run `examples/connect_usc.sh` from any working directory.
3. Ctrl-C closes the tunnel without logging out when
   `preserve_session_on_interrupt = true`. `disconnect usc` follows the saved
   `preserve_session` policy. Use `disconnect usc --logout` for an explicit logout.

To keep the original entry point, the suggested content of `../connect_vpn.sh` is:

```bash
#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/openconnect-saml/examples/connect_usc.sh" "$@"
```

For TUI, install the optional dependency if needed:

```bash
uv pip install --python .venv/bin/python -e '.[chrome,tui]'
sudo -v
.venv/bin/openconnect-saml --config "$HOME/.config/openconnect-saml/usc-manual.toml" tui
```

TUI connects using the saved profile's browser, username settings, and
`openconnect_args` (including vpn-slice). `[d]` disconnects the managed VPN
using its saved preservation policy, even if a different profile is selected.
Keep sudo credentials current before using the TUI: it suppresses child output,
so it is not a good place for interactive sudo/password prompts.

A valid cached VPN cookie skips browser startup in either CLI or TUI. A fresh
SSO login still requires the selected browser. Qt can fill a configured username
and accept a manually entered/pasted password, but has no native Apple Passwords
integration. Headless HTTP authentication does not host browser extensions and
cannot supply Apple's Passwords UI for interactive Duo flows.

If existing Qt rules only cover Azure's email input, add a username rule to the
existing HTTPS auto-fill rules for USC's form, for example:

```toml
[[auto_fill_rules."https://*"]]
selector = "input[name=username], input[name=j_username], input[id=username]"
fill = "username"
```

Existing explicitly saved rules are retained rather than replaced by new defaults.
The dedicated Chrome profile remains the option for using iCloud Passwords; see
[the browser guide](../docs/browsers.md#persistent-chrome-profile-and-apple-passwords-on-macos).

## Limits and verification

Session preservation does not override USC's expiry or revocation policy.
Ctrl-C preservation requires SIGHUP support (macOS/Linux) and uses sudo or
`--no-sudo`. Auth-only, detached, and kill-switch connections use fresh
authentication rather than attempting a cached cookie.

Qt has no native Apple Passwords integration. Safari is not an implemented
backend; normal Safari login would need a supported token-return mechanism.
Live USC/Duo login, iCloud Passwords authorization, and the native Qt UI still
need manual verification on the target machine.

Automated coverage includes real process-group SIGINT/SIGHUP delivery (including
the Python 3.10 compatibility path), generated Qt autofill JavaScript, saved
config and TUI policies, and rejection/refresh using an installed OpenConnect
against a localhost HTTPS gateway. The full local suite has five pre-existing
`tests/test_config_cmd.py` failures that also reproduce on the base commit.
