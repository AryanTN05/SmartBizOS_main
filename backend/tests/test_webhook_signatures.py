"""Tests for the webhook signature verifiers.

These guard a security-critical surface — the webhook router accepts
external traffic and, before this code, trusted an X-Tenant-Id header
that any caller could set. Pin the math + the replay window.
"""

import base64
import hashlib
import hmac
import time

from routers.webhooks import (
    _verify_tally, _verify_hubspot, _verify_svix,
    _HUBSPOT_REPLAY_WINDOW_S, _SVIX_REPLAY_WINDOW_S,
)


# ─── Tally ────────────────────────────────────────────────────────────────


def test_tally_valid_signature():
    secret = "tally_test_secret"
    body = b'{"data":{"fields":[{"label":"email","value":"a@b.com"}]}}'
    sig = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()
    assert _verify_tally(secret, body, sig) is True


def test_tally_wrong_signature():
    secret = "tally_test_secret"
    body = b"some body"
    assert _verify_tally(secret, body, "wrong_signature") is False


def test_tally_missing_signature():
    assert _verify_tally("secret", b"body", None) is False
    assert _verify_tally("secret", b"body", "") is False


def test_tally_wrong_secret():
    body = b"some body"
    sig = base64.b64encode(
        hmac.new(b"secret_a", body, hashlib.sha256).digest()
    ).decode()
    assert _verify_tally("secret_b", body, sig) is False


# ─── HubSpot v3 ───────────────────────────────────────────────────────────


def _make_hubspot_sig(secret: str, method: str, uri: str, body: bytes,
                      timestamp: str) -> str:
    msg = (method + uri + body.decode("utf-8") + timestamp).encode()
    return base64.b64encode(
        hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    ).decode()


def test_hubspot_valid_signature():
    secret = "hs_secret"
    body = b'{"event":"contact.creation"}'
    method = "POST"
    uri = "https://api.example.com/api/webhooks/hubspot"
    ts = str(int(time.time() * 1000))
    sig = _make_hubspot_sig(secret, method, uri, body, ts)
    ok, _ = _verify_hubspot(secret, method, uri, body, ts, sig)
    assert ok is True


def test_hubspot_wrong_signature():
    secret = "hs_secret"
    body = b'{"event":"x"}'
    ts = str(int(time.time() * 1000))
    ok, reason = _verify_hubspot(
        secret, "POST", "https://example.com/x", body, ts, "wrong_sig",
    )
    assert ok is False
    assert "signature" in reason.lower() or "match" in reason.lower()


def test_hubspot_replay_window():
    """Timestamps older than the window must reject — protects against
    replay attacks where a leaked signed payload is reused weeks later."""
    secret = "hs_secret"
    body = b"{}"
    method = "POST"
    uri = "https://example.com/x"
    # 2x the window in the past
    old_ts = str(int((time.time() - 2 * _HUBSPOT_REPLAY_WINDOW_S) * 1000))
    sig = _make_hubspot_sig(secret, method, uri, body, old_ts)
    ok, reason = _verify_hubspot(secret, method, uri, body, old_ts, sig)
    assert ok is False
    assert "replay" in reason.lower() or "window" in reason.lower()


def test_hubspot_missing_headers():
    ok, _ = _verify_hubspot("s", "POST", "/x", b"{}", None, "sig")
    assert ok is False
    ok, _ = _verify_hubspot("s", "POST", "/x", b"{}", "0", None)
    assert ok is False


def test_hubspot_replay_constant():
    """Pin the constant — changing the window in either direction has
    real security implications. Test exists to make the change loud."""
    assert _HUBSPOT_REPLAY_WINDOW_S == 5 * 60


# ─── Svix (Resend) ────────────────────────────────────────────────────────


def test_svix_valid_signature():
    """Svix format: secret is 'whsec_' + base64. Signature header carries
    one or more 'v1,base64' entries space-separated."""
    secret_raw = "test_key_for_svix"
    secret = "whsec_" + base64.b64encode(secret_raw.encode()).decode()
    body = b'{"type":"email.bounced"}'
    svix_id = "msg_test_123"
    svix_ts = str(int(time.time()))
    msg = f"{svix_id}.{svix_ts}.{body.decode()}".encode()
    digest = hmac.new(secret_raw.encode(), msg, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode()
    header = f"v1,{expected}"
    ok, _ = _verify_svix(secret, body, svix_id, svix_ts, header)
    assert ok is True


def test_svix_wrong_signature():
    secret_raw = "test_key"
    secret = "whsec_" + base64.b64encode(secret_raw.encode()).decode()
    ts = str(int(time.time()))
    ok, _ = _verify_svix(secret, b"{}", "msg_x", ts, "v1,wrong_sig")
    assert ok is False


def test_svix_stale_timestamp():
    secret_raw = "test_key"
    secret = "whsec_" + base64.b64encode(secret_raw.encode()).decode()
    body = b"{}"
    old_ts = str(int(time.time() - 2 * _SVIX_REPLAY_WINDOW_S))
    msg = f"x.{old_ts}.{body.decode()}".encode()
    digest = hmac.new(secret_raw.encode(), msg, hashlib.sha256).digest()
    sig = "v1," + base64.b64encode(digest).decode()
    ok, reason = _verify_svix(secret, body, "x", old_ts, sig)
    assert ok is False
    assert "replay" in reason.lower() or "window" in reason.lower()


def test_svix_multi_signature():
    """Svix can ship multiple signatures (v1,A v1,B). Either matching is
    a valid auth — accommodates secret rotation."""
    secret_raw = "test_key"
    secret = "whsec_" + base64.b64encode(secret_raw.encode()).decode()
    body = b"{}"
    ts = str(int(time.time()))
    msg = f"x.{ts}.{body.decode()}".encode()
    digest = hmac.new(secret_raw.encode(), msg, hashlib.sha256).digest()
    good = base64.b64encode(digest).decode()
    header = f"v1,wrongA v1,{good}"
    ok, _ = _verify_svix(secret, body, "x", ts, header)
    assert ok is True
