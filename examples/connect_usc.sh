#!/usr/bin/env bash
# USC launcher for this checkout; keeps the routing policy from ../connect_vpn.sh.
set -euo pipefail

repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
vpn_client="$repo_dir/.venv/bin/openconnect-saml"
config_path="${OPENCONNECT_SAML_CONFIG:-$HOME/.config/openconnect-saml/usc-manual.toml}"

if [[ ! -x "$vpn_client" ]]; then
  echo "Missing $vpn_client; install this checkout into .venv first." >&2
  exit 1
fi
if [[ ! -f "$config_path" ]]; then
  echo "Create $config_path from $repo_dir/examples/usc-manual.toml and set your NetID." >&2
  exit 1
fi
if ! vpn_slice="$(command -v vpn-slice)"; then
  echo "vpn-slice is not on PATH." >&2
  exit 1
fi
# OpenConnect executes --script as a shell command; quote the executable itself.
slice_command="$("$repo_dir/.venv/bin/python" -c \
  'import shlex, sys; print(shlex.join(sys.argv[1:]))' "$vpn_slice" 10.137.0.0/16)"

sudo -v
exec "$vpn_client" --config "$config_path" connect usc "$@" \
  -- --protocol=anyconnect --script "$slice_command"
