# Saved browser-managed SSO

`session-reuse.toml` is a generic example for a Cisco-compatible SAML gateway.
Replace the fictional gateway and username, then save it outside the checkout.
Its preservation settings explicitly opt into retaining the server session on
disconnect and Ctrl-C; the application defaults remain ordinary logout.

```bash
openconnect-saml --config /path/to/config.toml connect work
openconnect-saml disconnect work --logout
```

The example selects system Chrome and a dedicated persistent profile; install
the `[chrome]` extra and Google Chrome first. Use the same dedicated profile to
install any desired password-manager extension interactively before connecting.

For saved settings, see [configuration](../docs/configuration.md). For expected
cache, browser, and disconnect behavior, see [manual testing](../docs/manual-testing.md).
