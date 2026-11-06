# Configuration

`openconnect-saml` keeps state in a single TOML file. Default location:

- Linux: `~/.config/openconnect-saml/config.toml`
- macOS: `~/Library/Application Support/openconnect-saml/config.toml`
  (XDG-compatible if `XDG_CONFIG_HOME` is set)
- Windows: `%APPDATA%\openconnect-saml\config.toml`

The file is created automatically with mode `0600` on first save.

## Setup wizard

Easiest way to create the first profile:

```bash
openconnect-saml setup
openconnect-saml setup --advanced     # extra prompts for cert / hooks / kill-switch
```

Asks for: server URL, username, TOTP source (`local` / `2fauth` /
`bitwarden` / `1password` / `pass` / `none`), provider details if
applicable, browser backend, auto-reconnect, notifications, profile
name. Saves a profile and optionally sets it as the default.

`--advanced` adds a second pass of prompts for:

- Client certificate path + private key (per-profile `cert` /
  `cert_key`)
- `on_connect` / `on_disconnect` shell hook commands
- A boolean to enable per-profile kill-switch

The wizard also auto-discovers Cisco AnyConnect ``.xml`` profile
files at the standard locations (`/opt/cisco/anyconnect/profile`,
`/opt/cisco/secureclient/anyconnect/profile`, `~/.cisco/profile`)
and offers to bulk-import them on first run.

## Schema version

Configs carry a `schema_version` integer (currently `2` since v0.20.0).
Older configs without the field are treated as v1; the
``profiles migrate`` subcommand bumps them on demand:

```bash
openconnect-saml profiles migrate           # dry-run
openconnect-saml profiles migrate --apply
```

Current registered migrations:

- Lift legacy `[default_profile]` into `[profiles.default]`
- Drop unused `[2fauth]` / `[bitwarden]` / `[1password]` / `[pass]` /
  `[keepassxc]` sections
- Bump `schema_version` to the latest value

## TOML structure

```toml
# Behaviour flags
notifications = false
connection_history = true
token_cache = true
username_only = false
preserve_session = false
preserve_session_on_interrupt = false
on_connect = ""
on_disconnect = ""
timeout = 30
window_width = 800
window_height = 600

# Marks the most recently connected profile (set automatically)
active_profile = "work"

# Default profile picked when no name / --profile is given
[default_profile]
address = "vpn.example.com"
user_group = ""
name = "My VPN"

[credentials]
username = "user@example.com"
totp_source = "local"        # local | 2fauth | bitwarden | 1password | pass | none

# Named profiles (zero or more)
[profiles.work]
server = "vpn.company.com"
user_group = "employees"
name = "Work VPN"
routes = ["10.0.0.0/8"]
no_routes = ["192.168.0.0/16"]

[profiles.work.credentials]
username = "user@company.com"
totp_source = "1password"

# Provider sections (optional, only when used)
[2fauth]
url = "https://2fauth.example.com"
token = "eyJ0eXAiOiJKV1QiLC..."
account_id = 42

[bitwarden]
item_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[1password]
item = "vpn-work-mfa"
vault = "Engineering"

[pass]
entry = "vpn/work-totp"

[keepassxc]
database = "~/.keepass/secrets.kdbx"
entry = "Work/VPN-TOTP"
keyfile = ""    # optional .kdbx key-file (in addition to the master password)

[kill_switch]
enabled = false
allow_lan = false
ipv6 = true
dns_servers = ["1.1.1.1", "9.9.9.9"]

```

See [authentication.md](authentication.md) for full TOTP-provider
config details and [networking.md](networking.md) for kill-switch
options.

## Saved username, session policy, and Chrome settings

For USC, see the complete [example config](../examples/usc-manual.toml)
and [launcher](../examples/connect_usc.sh) on the `feat/usc-vpn-adaptation`
branch; see the [branch setup instructions](../examples/README.md).
Merge the relevant settings into
`~/.config/openconnect-saml/usc-manual.toml`; all top-level keys must come
before any `[table]` headers.

```toml
username_only = true
preserve_session = true
preserve_session_on_interrupt = true
chrome_channel = "chrome"
chrome_user_data_dir = "~/.local/share/openconnect-saml/usc-chrome"

[profiles.usc]
server = "https://vpn.usc.edu"
browser = "chrome"
openconnect_args = ["--protocol=anyconnect", "--script", "/opt/homebrew/bin/vpn-slice 10.137.0.0/16"]

[profiles.usc.credentials]
username = "YOUR_USC_NETID"
totp_source = "none"
```

Use your actual NetID and confirm the executable path with `command -v vpn-slice`.
An existing legacy config can instead use `[credentials]` for the username;
there is no need to repeat `--user` after saving it.

| Setting | Effect |
|---|---|
| `username_only` | Fill the saved username and leave password/MFA to the browser; no terminal password/TOTP prompts. |
| `preserve_session` | Default for `disconnect`, including TUI disconnect; use SIGHUP without logout. |
| `preserve_session_on_interrupt` | During a foreground tunnel, translate Ctrl-C to SIGHUP without logout. |
| `chrome_channel` | Select installed Chrome/Edge, including when launched through TUI. |
| `chrome_user_data_dir` | Reuse a dedicated Chrome profile and its installed extensions. |

The first three support per-profile overrides in `[profiles.usc]` as well as
top-level defaults. Explicit `false` in a profile overrides a top-level `true`.
The session record remembers its effective `preserve_session` policy, so
`disconnect usc` honors it even when the connection used a custom `--config`.

To explicitly log out once, use `disconnect usc --logout`. To keep the config
but use normal Ctrl-C logout for one connection, pass
`--no-preserve-session-on-interrupt`. CLI overrides do not rewrite saved policy.

Preservation requires SIGHUP (macOS/Linux). The Ctrl-C supervisor uses sudo
rather than doas (or `--no-sudo`) and validates sudo credentials before moving
OpenConnect into a separate process group. Browser login cancellation retains
its normal behavior. Server-side expiration and revocation still apply.

A saved profile's `openconnect_args` is used by CLI, GUI, and TUI connections.
An explicitly supplied CLI argument list after `--` replaces the saved list.
Keep the `--script` executable absolute, since sudo may use a different PATH.

## Auto-fill rules

Custom HTML-element fill rules for unusual IdP login pages:

```toml
[[auto_fill_rules."https://*"]]
selector = "input[type=email]"
fill = "username"

[[auto_fill_rules."https://*"]]
selector = "input[name=passwd]"
fill = "password"

[[auto_fill_rules."https://*"]]
selector = "input[id=idTxtBx_SAOTCC_OTC]"
fill = "totp"
```

Default rules cover Azure AD, Microsoft Account, and most Cisco IdPs.

## `config` subcommand

Inspect, validate, edit, diff, and merge config files:

```bash
openconnect-saml config path                # print resolved file path
openconnect-saml config show                # TOML, secrets redacted
openconnect-saml config show --json
openconnect-saml config validate            # schema + semantic checks
openconnect-saml config edit                # opens $EDITOR
openconnect-saml config diff OTHER.toml     # redacted unified diff
openconnect-saml config import OTHER.toml   # merge another config in
openconnect-saml config import OTHER.toml --force   # overwrite conflicts
```

`validate` catches:

- TOML syntax errors
- Missing `server` on a profile
- Unresolvable `active_profile`
- Missing `[2fauth]` / `[bitwarden]` / `[1password]` / `[pass]` /
  `[keepassxc]` sections referenced by a profile's `totp_source`
- Invalid CIDRs in `routes` / `no_routes`
- Overly-permissive file modes (anything other than `0600`)
- TOTP-provider binaries missing from `$PATH` (warns when a profile
  uses `1password` / `bitwarden` / `pass` / `keepassxc` but the
  corresponding `op` / `bw` / `pass` / `keepassxc-cli` isn't installed)

### diff vs. import

`config diff` produces a redacted unified diff against another TOML
file. Both sides go through the same redaction the `show` command
uses, so the output is safe to paste in bug reports / Slack.

`config import` deep-merges another TOML into the active config:

- Existing keys win by default — your overrides are safe.
- `--force` lets the incoming file replace overlapping keys.
- Dicts merge recursively. Lists / scalars are replaced wholesale.

## Overriding the config path

```bash
# CLI flag (per-invocation)
openconnect-saml --config /etc/openconnect-saml/work.toml status

# Environment variable (persistent in a shell)
export OPENCONNECT_SAML_CONFIG=/etc/openconnect-saml/work.toml
openconnect-saml status
```

Useful for multi-tenant setups, testing, and CI. The override applies
to every subcommand and the legacy CLI form.
