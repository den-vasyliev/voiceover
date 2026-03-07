import base64
import hashlib
import hmac as hmac_module
import json

from mcp_client.auth import HMACAuth


# ─── helper ───────────────────────────────────────────────────────────────────

def _expected_sig(key_bytes: bytes, params: dict) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hmac_module.new(key_bytes, payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


# ─── __init__ ────────────────────────────────────────────────────────────────

def test_init_valid_base64_decodes_key():
    raw = b"super_secret_key_32bytes_padding"
    auth = HMACAuth(base64.b64encode(raw).decode("utf-8"))
    assert auth.secret_key == raw


def test_init_invalid_base64_falls_back_to_raw_utf8():
    # A string whose length mod 4 == 1 is always an invalid base64 length,
    # which reliably triggers the except branch in HMACAuth.__init__.
    raw_key = "a"  # len=1, 1 % 4 == 1 → raises binascii.Error
    auth = HMACAuth(raw_key)
    assert auth.secret_key == raw_key.encode("utf-8")


# ─── sign_request ────────────────────────────────────────────────────────────

def test_sign_request_adds_auth_field():
    auth = HMACAuth(base64.b64encode(b"key").decode("utf-8"))
    signed = auth.sign_request({"tool": "echo"})
    assert "auth" in signed


def test_sign_request_signature_is_correct():
    raw = b"my-secret-key"
    auth = HMACAuth(base64.b64encode(raw).decode("utf-8"))
    params = {"tool": "search", "query": "planets"}
    signed = auth.sign_request(params)
    assert signed["auth"] == _expected_sig(raw, {"tool": "search", "query": "planets"})


def test_sign_request_strips_existing_auth_before_signing():
    raw = b"deterministic-key"
    auth = HMACAuth(base64.b64encode(raw).decode("utf-8"))
    sig_clean   = auth.sign_request({"action": "run"})["auth"]
    sig_tainted = auth.sign_request({"action": "run", "auth": "old_token"})["auth"]
    assert sig_clean == sig_tainted
    assert sig_clean == _expected_sig(raw, {"action": "run"})


def test_sign_request_does_not_mutate_original():
    auth = HMACAuth(base64.b64encode(b"key").decode("utf-8"))
    params = {"x": 1}
    auth.sign_request(params)
    assert params == {"x": 1}


def test_sign_request_empty_params():
    raw = b"key"
    auth = HMACAuth(base64.b64encode(raw).decode("utf-8"))
    signed = auth.sign_request({})
    assert signed == {"auth": _expected_sig(raw, {})}


def test_sign_request_raw_fallback_key_produces_correct_signature():
    # len=1 string is always an invalid base64 length, triggers the fallback.
    raw_key = "a"
    auth = HMACAuth(raw_key)
    params = {"n": 42}
    signed = auth.sign_request(params)
    assert signed["auth"] == _expected_sig(raw_key.encode("utf-8"), {"n": 42})
