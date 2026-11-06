# Session and browser reliability testing

This guide covers the development changes for session reuse, persistent browser
profiles, username-only login, and saved disconnect policies. Use an editable
checkout rather than a previously installed release. These checks complement
the automated tests and should be repeated against the gateway/browser versions
that will be used in practice.

## Prepare a profile

Install the required extras into a virtual environment:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e '.[dev,chrome,tui]'
```

If using system Chrome, set `chrome_channel = "chrome"`; bundled Chromium
requires a one-time `.venv/bin/playwright install chromium` instead. Qt requires
the `[gui]` extra. Create a separate config file using the following structure,
replace the fictional values, and keep top-level keys before table headers:

```toml
token_cache = true
username_only = true
preserve_session = true
preserve_session_on_interrupt = true
chrome_channel = "chrome"
chrome_user_data_dir = "~/.local/share/openconnect-saml/work-chrome"

[profiles.work]
server = "https://vpn.example.com"
browser = "chrome"
openconnect_args = ["--protocol=anyconnect"]

[profiles.work.credentials]
username = "user@example.com"
totp_source = "none"
```

The preservation settings above are explicit opt-ins for testing. The application
defaults are `false`. Use your usual route/script arguments in the saved profile
if the gateway requires them; explicit CLI arguments after `--` replace that list.
For commands below, replace `/path/to/test.toml` with the config file you created.

## Verify connection behavior

| Scenario | Action | Expected result |
|---|---|---|
| First login | Run `.venv/bin/openconnect-saml --config /path/to/test.toml connect work --forget-token`. | The browser opens; the saved username fills empty fields. No terminal VPN password/TOTP prompts appear. Complete the gateway's MFA manually. |
| Ctrl-C preservation | Press Ctrl-C with the foreground tunnel active. | OpenConnect disconnects using SIGHUP, restores network configuration, and the wrapper exits after cleanup. |
| Cookie reuse | Run the same connect command without `--forget-token`. | If the gateway still accepts the cookie, the connection starts without opening a browser or prompting for credentials. |
| Gateway rejection | After the gateway expires or revokes the saved session, reconnect. | The rejected cache entry is removed; one fresh browser SSO login is attempted. Rejection of the fresh cookie ends the attempt rather than looping. |
| Explicit logout | While connected, run `.venv/bin/openconnect-saml disconnect work --logout` from another terminal. | The VPN session is logged out. A later connection may reject the old cookie and require SSO again. |
| Configured disconnect | Run `.venv/bin/openconnect-saml disconnect work` from another terminal. | The connection's saved preservation policy applies, even though the connect command used a custom config path. |
| Cache disabled | Connect with `--no-token-cache`. | Fresh SSO is used; existing cached entries are not read, overwritten, or deleted by a subsequent rejection. |
| Default logout behavior | Connect with `--no-preserve-session-on-interrupt`, then press Ctrl-C. | Ordinary OpenConnect SIGINT logout is retained. |
| Network/setup failure | Attempt a cached connection when the endpoint is unavailable or local tunnel setup fails. | The failure is reported without treating it as an authentication rejection and opening SSO. |

A displayed expiry is an upper bound: gateway logout, inactivity limits, IP
changes, or server policy can make a cookie unusable sooner. `--forget-token`
forces a fresh login; it does not simulate the automatic rejection path. A
working keyring is needed for reuse across invocations. Losing access to the
keyring should still permit fresh authentication.

## Verify browsers and TUI

- **Persistent Chrome:** close the login browser after authentication and later
  force fresh SSO. The dedicated profile should retain site storage and installed
  extensions. Install any desired password-manager extension interactively in
  that same profile first. Apple Passwords authorization remains interactive.
- **Username-only behavior:** check an IdP page with username and password on the
  same form. The username should fill without submitting an incomplete form.
  A password entered by you or an extension must not be overwritten.
- **Qt:** connect with `--browser qt` after installing `[gui]`. Check username
  autofill and manual password entry, including existing custom autofill rules.
  This backend has no native Apple Passwords integration. The generated script
  tests do not establish native UI or WebAuthn compatibility.
- **TUI:** validate sudo credentials first (`sudo -v`), then run
  `.venv/bin/openconnect-saml --config /path/to/test.toml tui`. Connect the saved
  profile and check that its browser and OpenConnect arguments are applied.
  Selecting a different row before pressing `d` must still disconnect the
  profile that the TUI started, using its saved policy.
- **Other accounts/gateways:** verify that cache entries remain isolated by
  gateway, login groups, username, and named profile. Redirected authentication
  must reconnect to the stored final gateway with the corresponding certificate pin.

Chrome automation must use a dedicated user-data directory, not your everyday
browser profile. TUI is a launcher and monitor; interactive SSO still needs the
selected browser when the gateway requires a fresh login.

## Platform and mode coverage

Ctrl-C preservation requires SIGHUP and supports macOS/Linux with sudo or
`--no-sudo`. Default Windows behavior should remain unchanged; opting into an
unsupported preservation mode must produce a clear failure. Validate real sudo
signal forwarding on the target machine; the automated supervisor test uses a
harmless privilege-wrapper stand-in.

Auth-only, detached, and kill-switch modes deliberately use fresh authentication.
The detached launcher does not observe a later cookie rejection, and an active
kill-switch can block a subsequent IdP/MFA refresh. Confirm these modes retain
their normal connection behavior. Safari is not an implemented browser backend.

## Automated checks and PR evidence

```bash
PYTHON_KEYRING_BACKEND=keyring.backends.null.Keyring .venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check openconnect_saml tests
```

The null backend prevents tests from accessing real keyring credentials. Tests
that need persistence use an isolated in-memory keyring. Running the full suite
requires localhost sockets for the mock HTTPS gateways. Additional coverage:

- Real process-group SIGINT/SIGHUP delivery, including the Python 3.10 fallback.
- Installed OpenConnect rejecting cookies against a localhost HTTPS gateway;
  skipped when the binary is unavailable.
- Execution of generated Qt autofill JavaScript; skipped when Node is unavailable.
- Mocked Playwright persistence and cleanup; optional tests skip without Playwright.

Before submitting a PR, record the OS, Python/OpenConnect/browser versions,
identity-provider/MFA flow, and results of the relevant scenarios above. Identify
skipped or untested paths explicitly. Automated mocks and local protocol checks
are not evidence of live gateway, native Qt UI, password-manager extension, or
cross-platform CI reliability. Run the existing CI matrix before merging or
releasing; this guide does not replace it.
