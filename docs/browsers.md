# Browser backends

`openconnect-saml` drives the SAML/SSO flow in one of three browser
backends. Pick the one that matches your setup with `--browser`:

| Backend | Flag | Best for |
|---|---|---|
| **Headless** | `--headless` *or* `--browser headless` | Servers, containers, CI |
| **Qt6 WebEngine** | `--browser qt` *(default with `[gui]`)* | Desktop, full IdP UI |
| **Chrome / Chromium** | `--browser chrome` | Hardware tokens, Duo, Azure number-matching |

## Headless

No display required. Two-stage authentication:

1. **Auto** — HTTP + form-parser submits credentials directly.
2. **Fallback** — if auto fails (CAPTCHA, unusual MFA), the CLI prints
   a URL and starts a local callback server. Open the URL in any
   browser on any device, complete login, and the callback finishes
   the flow.

```bash
# Auto-authenticate with saved credentials
openconnect-saml --server vpn.example.com --headless --user user@example.com

# Auth-only mode — emit cookie, don't connect
openconnect-saml --server vpn.example.com --headless --authenticate json
openconnect-saml --server vpn.example.com --headless --authenticate shell
```

## Qt6 WebEngine

The default when the `[gui]` extra is installed. Fully-featured
embedded browser with WebAuthn / FIDO2 support since v0.8.2 (requires
QtWebEngine ≥ 6.7).

```bash
openconnect-saml --server vpn.example.com               # legacy invocation
openconnect-saml connect work --browser qt              # explicit
```

The Qt browser handles `webAuthUxRequested` so YubiKey / Nitrokey LEDs
light up on Duo / Cisco prompts.

## Chrome / Chromium (Playwright)

Visible Chromium window, native WebAuthn (FIDO2 hardware keys work
out of the box), recommended for unusual MFA flows where Qt struggles
or for FIDO2-only tenants:

```bash
openconnect-saml --server vpn.example.com --browser chrome
openconnect-saml connect work --browser chrome
openconnect-saml --server vpn.example.com --browser chrome --browser-display-mode hidden
```

Requires `pip install "openconnect-saml[chrome]"` (or AUR
`python-playwright` — **not** `aur/playwright`, which is the
Node.js library) and a one-time `playwright install chromium` to
download the ~150 MB Chromium bundle.

### Skipping the Playwright Chromium download

If you already have Chrome / Edge installed system-wide, point
Playwright at it via `--chrome-channel`:

```bash
openconnect-saml connect work --browser chrome --chrome-channel chrome
# or msedge / chrome-beta / chrome-dev / chrome-canary / msedge-beta / …
```

Valid channels: `chrome`, `chrome-beta`, `chrome-dev`, `chrome-canary`,
`msedge`, `msedge-beta`, `msedge-dev`, `msedge-canary`. Plain
`chromium` is **not** a Playwright channel — Arch's stock
`pacman -S chromium` users either install AUR `google-chrome`
(then `--chrome-channel chrome`), or just run
`playwright install chromium` once (it caches under
`~/.cache/ms-playwright/` and never re-downloads). Full caveat in
[authentication.md](authentication.md#saving-the-150-mb-chromium-download).

## Minimal profile GUI

For a Cisco-Secure-Client-style launcher around saved profiles:

```bash
openconnect-saml gui
```

A small Tk window listing profiles, a Browser dropdown
(chrome / qt / headless — picks per-launch), Connect / Disconnect /
Refresh buttons, and a live process log. Intentionally minimal —
advanced flags still go through the CLI.

## Display modes for Qt

Useful for debugging or running under Wayland without window decorations:

```bash
--browser-display-mode shown    # default
--browser-display-mode hidden   # platform=minimal Qt plugin (off-screen)
```

## Window size for Qt

```bash
--window-size 1024x768
```

Or persistently in `config.toml`:

```toml
window_width = 1024
window_height = 768
```

## Reusing VPN sessions

VPN session cookies are cached by default in the OS keyring (macOS Keychain
on macOS), under the separate `openconnect-saml/session` service. Entries
are scoped to the gateway URL, login groups, username, and named profile.
The cookie, authenticated gateway URL (including redirects), and gateway
certificate fingerprint are saved together; the cookie never goes into `config.toml`.
If no keyring is available, authentication continues normally without caching.

On the next foreground connection, the saved cookie is sent to OpenConnect
before opening a browser or prompting for credentials. If the gateway rejects
it (OpenConnect exit status 2), the entry is removed and a fresh SSO login is
attempted once with your selected browser. Network and local setup errors do
not trigger a login. `--reconnect` also uses this behavior.

- `--forget-token`: delete the entry for this account/gateway and log in again.
- `--no-token-cache`: skip cache reads and writes for this invocation.
- `token_cache = false` in top-level config: disable caching persistently.

Auth-only (`--authenticate`) and detached (`--detach`) invocations always use
fresh authentication. The detached launcher cannot observe a later cookie
rejection from its background process. Kill-switch connections also authenticate
fresh before enabling the firewall, since the firewall would block IdP/Duo
access during a later browser refresh.

A server's “14 days” message does not guarantee a cookie will remain reusable
for 14 days: the VPN and the identity provider can expire or revoke sessions
independently. More specifically, **by default Ctrl-C and ordinary `disconnect` log the
VPN session out**, so the saved cookie can no longer reconnect that session.
Keeping an invalidated cookie on disk does not restore a logged-out session.

On macOS/Linux, you can deliberately disconnect a recorded session without
logging out:

```bash
# From another terminal while a normal foreground connection is running:
openconnect-saml disconnect default --preserve-session
# Or use your saved profile's name instead of "default".
```

This sends SIGHUP rather than SIGTERM. The tunnel closes and network cleanup
runs, but OpenConnect does not send a logout. USC can still expire or revoke
the session. This does not background a running VPN: `--detach` keeps a
tunnel running in the background, whereas SIGHUP closes it while retaining
the server session. See [OpenConnect's signal documentation](https://www.infradead.org/openconnect/manual.html#heading5).

To make preservation your saved policy instead of repeating flags, put these
at the top of your config (or override them in a named profile):

```toml
preserve_session = true
preserve_session_on_interrupt = true
username_only = true
```

`preserve_session` controls `disconnect`; `preserve_session_on_interrupt`
controls Ctrl-C during a foreground tunnel. `disconnect --logout` and
`--no-preserve-session-on-interrupt` provide explicit per-invocation overrides.
The Ctrl-C supervisor keeps OpenConnect in a separate process group so a
terminal SIGINT cannot log the VPN session out before the wrapper sends SIGHUP.
It waits for OpenConnect to exit and run network cleanup. This path uses sudo
(or `--no-sudo`) on macOS/Linux; defaults remain unchanged when it is disabled.
See the [USC example](../examples/README.md) for the existing launcher and TUI.

## Persistent Chrome profile and Apple Passwords on macOS

Use a dedicated profile to retain SSO/Duo cookies, site storage, browser
preferences, and installed extensions between runs:

```bash
openconnect-saml --server YOUR_USC_VPN_HOST --browser chrome \
  --chrome-channel chrome \
  --chrome-user-data-dir "$HOME/.local/share/openconnect-saml/usc-chrome" \
  --user YOUR_USC_NETID --username-only
```

`--username-only` fills the username without reading saved passwords/TOTP or
asking for them in the terminal. Your username is saved in the config for
later runs; continue passing `--username-only` or set `username_only = true`.
This lets the browser's password manager handle the password, while you
complete Duo normally. In Chrome this mode leaves form submission and MFA
choices to you, avoiding submission of an incomplete username/password form.
**`--user` alone keeps the original terminal password prompt** if no password
is saved; after that, browser authentication still opens. Browser storage may
also remember the username if
the identity provider supports that behavior.

Persist the following at the **top level**, before any `[table]` headers in
your existing `config.toml`:

```toml
chrome_user_data_dir = "~/.local/share/openconnect-saml/usc-chrome"
username_only = true
chrome_channel = "chrome"
```

Use a separate directory from your everyday Chrome profile. Playwright does
not support automating Chrome's default profile, and two running browser
instances cannot share one user-data directory. Close the dedicated browser
before connecting again.

To install extensions without racing the login window's timeout, open that
same dedicated profile manually first:

```bash
open -na "Google Chrome" --args \
  --user-data-dir="$HOME/.local/share/openconnect-saml/usc-chrome"
```

Install Apple's **iCloud Passwords** extension there (Passwords app →
Passwords → Get Browser Extension), complete any authorization it requires,
then quit that Chrome instance. Subsequent VPN login windows reuse that
profile and allow its installed extensions. Extension installation and
Apple Passwords authorization still require user interaction. Actual
compatibility must be checked on your macOS/Chrome versions.
The persistent browser uses the normal OS credential store instead of
Playwright's mock Keychain/basic-password-store defaults, so Chrome may ask
you to authorize Keychain access. This is separate from the application's
VPN-cookie keyring entry and from iCloud Passwords extension authorization.

This preserves extensions installed through the browser; it does not sideload
extensions. Current Chrome/Edge removed the command-line sideloading flags.
See [Apple's extension setup](https://support.apple.com/guide/passwords/get-extensions-mchlf7ac261e/mac),
[Playwright persistent contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context),
and [extension support](https://playwright.dev/python/docs/chrome-extensions).

### Qt, headless, and Safari limitations

The existing Qt WebEngine backend has no native Apple Passwords integration.
Adding a context menu entry alone would not connect it to Apple's credential
provider. The OS keyring used here stores application secrets separately;
it does not automatically read website passwords from the Passwords app.
A native macOS integration would be a separate development effort.

TUI changes the launcher UI. It honors the saved profile browser, OpenConnect
arguments (including vpn-slice), and disconnect policy; a cached VPN cookie
can avoid starting any browser. HTTP headless authentication has no browser
extension host for iCloud Passwords. Session reuse avoids launching any
browser while a cached VPN cookie remains accepted; use Chrome for Duo when
a new browser login is necessary.

Safari is not a supported backend. Playwright's WebKit is separate from
installed Safari and its profile. Safari WebDriver runs in isolated automation
windows without normal browsing AutoFill data, so it would not solve the
Password AutoFill requirement. While WebDriver is active, Safari also blocks
manual mouse/keyboard interaction with those windows; taking manual control
ends the automation session. This is not a prompt that grants the program
access to your normal Safari passwords. Supporting the normal Safari session would
require a separate token-return mechanism (for example a compatible gateway
callback or a Safari extension), beyond selecting a browser executable.
OpenConnect has an `--external-browser` option for gateways that explicitly
support `single-sign-on-external-browser`; this repository currently requests
the different `single-sign-on-v2` flow, and USC support for the external-browser
flow has not been verified. Merely opening the current login URL in Safari
does not return its cookie to this application.
See [Apple's Safari WebDriver documentation](https://developer.apple.com/documentation/webkit/about-webdriver-for-safari).
