"""Confirm the exit-code assumption with the installed OpenConnect binary."""

import base64
import shutil
import subprocess
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

from openconnect_saml import app, config, token_cache
from openconnect_saml.authenticator import AuthCompleteResponse
from tests.integration.mock_saml_gateway import MockGateway, _Handler


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("openconnect") is None, reason="OpenConnect binary unavailable")
def test_real_openconnect_rejects_saved_cookie_and_refreshes_once(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    vault = {}
    monkeypatch.setattr(token_cache.keyring, "get_password", lambda s, k: vault.get((s, k)))
    monkeypatch.setattr(
        token_cache.keyring, "set_password", lambda s, k, v: vault.__setitem__((s, k), v)
    )
    monkeypatch.setattr(
        token_cache.keyring, "delete_password", lambda s, k: vault.pop((s, k), None)
    )
    sent = []

    def reject_cookie(handler):
        sent.append(handler.headers.get("Cookie"))
        handler.send_response(401)
        handler.send_header("Content-Length", "0")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True

    monkeypatch.setattr(_Handler, "do_CONNECT", reject_cookie, raising=False)
    monkeypatch.setattr(_Handler, "protocol_version", "HTTP/1.1")
    with MockGateway(host="127.0.0.1") as gateway:
        cert = x509.load_pem_x509_certificate(gateway._cert_path.read_bytes())
        # OpenConnect pins the public key, rather than the certificate DER.
        digest = hashes.Hash(hashes.SHA256())
        digest.update(
            cert.public_key().public_bytes(
                serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        pin = "pin-sha256:" + base64.b64encode(digest.finalize()).decode()
        host = config.HostProfile(gateway.url, "", "")
        cached = AuthCompleteResponse("success", "", "saved-cookie", pin)
        fresh = AuthCompleteResponse("success", "", "fresh-cookie", pin)
        options = SimpleNamespace(
            proxy=None,
            ac_version="4.7.00136",
            openconnect_args=[],
            _using_cached_token=True,
            _token_cache_key="key",
        )
        token_cache.save("key", cached, host)
        invoke = subprocess.run

        def run_with_deadline(*a, **kw):
            return invoke(*a, timeout=10, **kw)

        with (
            patch.object(app, "_run", AsyncMock(return_value=(fresh, host))) as refresh,
            patch.object(app.config, "save"),
            patch.object(app.subprocess, "run", side_effect=run_with_deadline),
        ):
            result = app._connect_with_token_refresh(
                options, config.Config(), cached, host, no_sudo=True
            )
    assert result == 2
    assert sent == ["webvpn=saved-cookie", "webvpn=fresh-cookie"]
    refresh.assert_awaited_once()
    assert token_cache.load("key") is None
