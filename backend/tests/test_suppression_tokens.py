"""Tests for the unsubscribe token (HMAC) layer.

Verifies tamper-resistance + roundtrip parsing without DB access.
"""

import os
import uuid

from automations.suppression import (
    make_unsubscribe_token, verify_unsubscribe_token,
    parse_lead_id_from_token, public_unsubscribe_url,
    list_unsubscribe_headers,
)


def test_token_roundtrip():
    lead = uuid.uuid4()
    tenant = uuid.uuid4()
    token = make_unsubscribe_token(lead, tenant)
    assert verify_unsubscribe_token(token, lead, tenant) is True
    assert parse_lead_id_from_token(token) == lead


def test_token_rejects_wrong_tenant():
    lead = uuid.uuid4()
    tenant = uuid.uuid4()
    other = uuid.uuid4()
    token = make_unsubscribe_token(lead, tenant)
    assert verify_unsubscribe_token(token, lead, other) is False


def test_token_rejects_wrong_lead():
    """A token signed for lead A must NOT verify when paired with lead B,
    even if tenant matches. Otherwise an attacker who unsubscribes their
    own lead could opt out other leads in the same workspace."""
    a = uuid.uuid4()
    b = uuid.uuid4()
    tenant = uuid.uuid4()
    token = make_unsubscribe_token(a, tenant)
    assert verify_unsubscribe_token(token, b, tenant) is False


def test_token_rejects_garbage():
    lead = uuid.uuid4()
    tenant = uuid.uuid4()
    assert verify_unsubscribe_token("", lead, tenant) is False
    assert verify_unsubscribe_token("nodot", lead, tenant) is False
    assert verify_unsubscribe_token("garbage.token", lead, tenant) is False


def test_token_format():
    """Token shape: 'b64url(lead_id_str).hex_signature'. Pin the format
    so any future change is intentional."""
    lead = uuid.uuid4()
    tenant = uuid.uuid4()
    token = make_unsubscribe_token(lead, tenant)
    assert "." in token
    head, sig = token.split(".", 1)
    assert len(sig) == 32  # 32 hex chars = 128 bits, plenty
    # head decodes back to the lead's UUID string.
    assert parse_lead_id_from_token(token) == lead


def test_secret_change_invalidates_tokens():
    """Rotating UNSUBSCRIBE_SECRET invalidates outstanding tokens —
    tested by setting the env, generating a token, switching, verifying."""
    saved = os.environ.get("UNSUBSCRIBE_SECRET")
    try:
        os.environ["UNSUBSCRIBE_SECRET"] = "secret-A"
        lead = uuid.uuid4()
        tenant = uuid.uuid4()
        token = make_unsubscribe_token(lead, tenant)
        assert verify_unsubscribe_token(token, lead, tenant) is True

        os.environ["UNSUBSCRIBE_SECRET"] = "secret-B"
        assert verify_unsubscribe_token(token, lead, tenant) is False
    finally:
        if saved is None:
            os.environ.pop("UNSUBSCRIBE_SECRET", None)
        else:
            os.environ["UNSUBSCRIBE_SECRET"] = saved


def test_unsubscribe_url_contains_token():
    saved = os.environ.get("PUBLIC_API_ORIGIN")
    try:
        os.environ["PUBLIC_API_ORIGIN"] = "https://api.example.com"
        url = public_unsubscribe_url(uuid.uuid4(), uuid.uuid4())
        assert url.startswith("https://api.example.com/api/u/")
        assert "." in url.split("/api/u/")[-1]  # token has a separator
    finally:
        if saved is None:
            os.environ.pop("PUBLIC_API_ORIGIN", None)
        else:
            os.environ["PUBLIC_API_ORIGIN"] = saved


def test_list_unsubscribe_headers_rfc8058():
    h = list_unsubscribe_headers(uuid.uuid4(), uuid.uuid4())
    # RFC 2369 header
    assert "List-Unsubscribe" in h
    assert h["List-Unsubscribe"].startswith("<") and h["List-Unsubscribe"].endswith(">")
    # RFC 8058 — what makes Gmail/Outlook one-click work
    assert h["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
