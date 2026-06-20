"""Tests for the IMAP poller's pure helpers.

Specifically the RFC 3834 Auto-Submitted parser — a regression here
silently drops real replies, which is the worst possible failure mode
of the entire reply-detection feature.
"""

from automations.imap_poller import _is_auto_reply, _extract_email


# ─── RFC 3834 Auto-Submitted ──────────────────────────────────────────────


def test_auto_submitted_no_passes_through():
    """Header value 'no' is the conformant way to say 'human'."""
    assert _is_auto_reply({"auto-submitted": "no"}, "real reply") is False


def test_auto_submitted_no_with_params_passes():
    """Real-world: 'no, private' or 'no; type=text'. Past versions
    treated these as auto-submitted and silently dropped legitimate
    replies. Pin the fix."""
    assert _is_auto_reply({"auto-submitted": "no, private"}, "real reply") is False
    assert _is_auto_reply({"auto-submitted": "no; type=text"}, "real reply") is False
    assert _is_auto_reply({"auto-submitted": "  no  "}, "real reply") is False


def test_auto_submitted_auto_replied_blocked():
    assert _is_auto_reply({"auto-submitted": "auto-replied"}, "subj") is True
    assert _is_auto_reply({"auto-submitted": "auto-generated"}, "subj") is True
    assert _is_auto_reply({"auto-submitted": "auto-notified"}, "subj") is True


def test_auto_submitted_with_params_still_blocked():
    assert _is_auto_reply({"auto-submitted": "auto-replied; type=vacation"}, "subj") is True


def test_auto_submitted_case_insensitive():
    assert _is_auto_reply({"auto-submitted": "AUTO-REPLIED"}, "subj") is True


def test_auto_response_suppress_blocks():
    assert _is_auto_reply({"x-auto-response-suppress": "OOF"}, "subj") is True


def test_precedence_blocks_bulk():
    assert _is_auto_reply({"precedence": "bulk"}, "subj") is True
    assert _is_auto_reply({"precedence": "junk"}, "subj") is True
    assert _is_auto_reply({"precedence": "auto_reply"}, "subj") is True


def test_subject_ooo_prefix():
    """Many auto-responders put 'Out of office:' at the start of the
    subject without setting Auto-Submitted. Catch those."""
    assert _is_auto_reply({}, "Out of office: away until Monday") is True


def test_real_reply_passes_through():
    """The whole point: human replies must NOT be classified as auto."""
    assert _is_auto_reply({}, "Sounds great, let's chat Tuesday") is False
    assert _is_auto_reply({"auto-submitted": ""}, "Sounds great") is False


# ─── _extract_email (From header parser) ──────────────────────────────────


def test_extract_email_from_named_format():
    """'Alice <alice@example.com>' → 'alice@example.com'."""
    assert _extract_email('"Alice" <alice@example.com>') == "alice@example.com"


def test_extract_email_bare():
    assert _extract_email("alice@example.com") == "alice@example.com"


def test_extract_email_empty():
    assert _extract_email("") is None
    assert _extract_email(None) is None


def test_extract_email_lowercases():
    assert _extract_email("Alice@EXAMPLE.COM") == "alice@example.com"
