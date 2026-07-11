"""Tests for tau_coding.oauth module."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from tau_coding.oauth import (  # type: ignore[attr-defined]
    OPENAI_CODEX_ACCOUNT_CLAIM,
    OPENAI_CODEX_AUTHORIZE_URL,
    OPENAI_CODEX_CLIENT_ID,
    OPENAI_CODEX_REDIRECT_URI,
    TOKEN_REFRESH_SKEW_MS,
    OAuthCredential,
    OAuthError,
    TokenResponse,
    _access_token_expiry,
    _access_token_payload,
    _base64url,
    _base64url_decode,
    _first_query_value,
    _oauth_html,
    _optional_token_field,
    _required_token_field,
    _token_expiry,
    _validate_state,
    account_id_from_access_token,
    create_openai_codex_authorization_flow,
    create_pkce_pair,
    exchange_openai_codex_authorization_code,
    oauth_credential_is_expired,
    parse_authorization_input,
    refresh_openai_codex_token,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_jwt(payload: dict[str, object]) -> str:
    """Create an unsigned JWT-like token for testing."""
    header = _base64url(json.dumps({"alg": "none"}).encode())
    body = _base64url(json.dumps(payload).encode())
    return f"{header}.{body}."


def _expired_token_payload() -> dict[str, object]:
    return {
        OPENAI_CODEX_ACCOUNT_CLAIM: {"chatgpt_account_id": "acct_test123"},
        "exp": int(time.time()) - 3600,
    }


def _fresh_token_payload() -> dict[str, object]:
    return {
        OPENAI_CODEX_ACCOUNT_CLAIM: {"chatgpt_account_id": "acct_test123"},
        "exp": int(time.time()) + 3600,
    }


# ── PKCE ─────────────────────────────────────────────────────────────────────


class TestCreatePkcePair:
    def test_returns_verifier_and_challenge(self) -> None:
        verifier, challenge = create_pkce_pair()
        assert isinstance(verifier, str)
        assert len(verifier) > 0
        assert isinstance(challenge, str)
        assert len(challenge) > 0
        assert verifier != challenge


class TestCreateOpenaiCodexAuthorizationFlow:
    def test_returns_flow_with_url(self) -> None:
        flow = create_openai_codex_authorization_flow()
        assert isinstance(flow.verifier, str)
        assert isinstance(flow.state, str)
        assert flow.url.startswith(OPENAI_CODEX_AUTHORIZE_URL)
        assert OPENAI_CODEX_CLIENT_ID in flow.url
        # The redirect_uri is URL-encoded in the query string
        from urllib.parse import quote
        assert quote(OPENAI_CODEX_REDIRECT_URI, safe="") in flow.url
        assert "scope=" in flow.url

    def test_originator_param(self) -> None:
        flow = create_openai_codex_authorization_flow(originator="test-originator")
        assert "test-originator" in flow.url

    def test_includes_code_challenge(self) -> None:
        flow = create_openai_codex_authorization_flow()
        assert "code_challenge=" in flow.url
        assert "code_challenge_method=S256" in flow.url


# ── parse_authorization_input ────────────────────────────────────────────────


class TestParseAuthorizationInput:
    def test_empty_string(self) -> None:
        result = parse_authorization_input("")
        assert result.code is None
        assert result.state is None

    def test_whitespace_only(self) -> None:
        result = parse_authorization_input("   ")
        assert result.code is None
        assert result.state is None

    def test_raw_code(self) -> None:
        result = parse_authorization_input("abc123")
        assert result.code == "abc123"
        assert result.state is None

    def test_full_url(self) -> None:
        url = f"{OPENAI_CODEX_REDIRECT_URI}?code=thecode&state=thestate"
        result = parse_authorization_input(url)
        assert result.code == "thecode"
        assert result.state == "thestate"

    def test_url_without_query(self) -> None:
        url = "http://localhost:1455/auth/callback"
        result = parse_authorization_input(url)
        assert result.code is None
        assert result.state is None

    def test_code_hash_state(self) -> None:
        result = parse_authorization_input("mycode#mystate")
        assert result.code == "mycode"
        assert result.state == "mystate"

    def test_code_hash_only(self) -> None:
        result = parse_authorization_input("codeonly#")
        assert result.code == "codeonly"
        assert result.state is None

    def test_query_string(self) -> None:
        result = parse_authorization_input("code=abc&state=def")
        assert result.code == "abc"
        assert result.state == "def"

    def test_query_string_missing_state(self) -> None:
        result = parse_authorization_input("code=abc")
        assert result.code == "abc"
        assert result.state is None


# ── credential expiry ────────────────────────────────────────────────────────


class TestOauthCredentialIsExpired:
    def test_expired_credential(self) -> None:
        cred = OAuthCredential(
            access="a",
            refresh="r",
            expires=1,  # epoch 1 ms → long expired
            account_id="acct",
        )
        assert oauth_credential_is_expired(cred) is True

    def test_fresh_credential(self) -> None:
        far_future = int(time.time() * 1000) + 3600_000  # 1 hour from now
        cred = OAuthCredential(
            access="a",
            refresh="r",
            expires=far_future,
            account_id="acct",
        )
        assert oauth_credential_is_expired(cred) is False

    def test_about_to_expire_within_skew(self) -> None:
        almost_expired = int(time.time() * 1000) + TOKEN_REFRESH_SKEW_MS - 1000
        cred = OAuthCredential(
            access="a",
            refresh="r",
            expires=almost_expired,
            account_id="acct",
        )
        assert oauth_credential_is_expired(cred) is True


# ── JWT / account_id ─────────────────────────────────────────────────────────


class TestAccessTokenPayload:
    def test_valid_token(self) -> None:
        payload = _fresh_token_payload()
        token = _make_jwt(payload)
        result = _access_token_payload(token)
        assert result is not None
        assert result[OPENAI_CODEX_ACCOUNT_CLAIM]["chatgpt_account_id"] == "acct_test123"

    def test_malformed_token(self) -> None:
        assert _access_token_payload("not-a-jwt") is None

    def test_too_few_parts(self) -> None:
        assert _access_token_payload("one.two") is None

    def test_invalid_base64(self) -> None:
        assert _access_token_payload("x.y!.z") is None

    def test_non_dict_payload(self) -> None:
        # A valid JWT structure with a non-dict payload
        header = _base64url(json.dumps({"alg": "none"}).encode())
        body = _base64url(json.dumps("justastring").encode())
        token = f"{header}.{body}."
        assert _access_token_payload(token) is None


class TestAccessTokenExpiry:
    def test_returns_expiry(self) -> None:
        payload = _fresh_token_payload()
        token = _make_jwt(payload)
        exp = _access_token_expiry(token)
        assert isinstance(exp, int)
        assert exp > int(time.time() * 1000)

    def test_none_for_invalid_token(self) -> None:
        assert _access_token_expiry("bad") is None

    def test_none_for_no_exp(self) -> None:
        token = _make_jwt({"sub": "no-exp"})
        assert _access_token_expiry(token) is None


class TestAccountIdFromAccessToken:
    def test_valid_token(self) -> None:
        token = _make_jwt(_fresh_token_payload())
        result = account_id_from_access_token(token)
        assert result == "acct_test123"

    def test_malformed_token(self) -> None:
        assert account_id_from_access_token("bad") is None

    def test_missing_claim_key(self) -> None:
        token = _make_jwt({"sub": "no-claim"})
        assert account_id_from_access_token(token) is None

    def test_non_dict_claim(self) -> None:
        token = _make_jwt({OPENAI_CODEX_ACCOUNT_CLAIM: "not-a-dict"})
        assert account_id_from_access_token(token) is None

    def test_missing_account_id(self) -> None:
        token = _make_jwt({OPENAI_CODEX_ACCOUNT_CLAIM: {}})
        assert account_id_from_access_token(token) is None

    def test_empty_account_id(self) -> None:
        token = _make_jwt({OPENAI_CODEX_ACCOUNT_CLAIM: {"chatgpt_account_id": "  "}})
        assert account_id_from_access_token(token) is None


# ── token field helpers ──────────────────────────────────────────────────────


class TestRequiredTokenField:
    def test_returns_value(self) -> None:
        assert _required_token_field({"access_token": "abc"}, "access_token", action="test") == "abc"  # noqa: E501

    def test_missing_field(self) -> None:
        with pytest.raises(OAuthError, match="test"):
            _required_token_field({"other": "x"}, "access_token", action="test")

    def test_empty_string(self) -> None:
        with pytest.raises(OAuthError, match="test"):
            _required_token_field({"access_token": ""}, "access_token", action="test")

    def test_non_string(self) -> None:
        with pytest.raises(OAuthError, match="test"):
            _required_token_field({"access_token": 123}, "access_token", action="test")


class TestOptionalTokenField:
    def test_returns_value(self) -> None:
        assert _optional_token_field({"refresh_token": "abc"}, "refresh_token") == "abc"

    def test_none_for_missing(self) -> None:
        assert _optional_token_field({"other": "x"}, "refresh_token") is None

    def test_none_for_empty(self) -> None:
        assert _optional_token_field({"refresh_token": ""}, "refresh_token") is None

    def test_none_for_non_string(self) -> None:
        assert _optional_token_field({"refresh_token": 123}, "refresh_token") is None


# ── token expiry ─────────────────────────────────────────────────────────────


class TestTokenExpiry:
    def test_uses_expires_in(self) -> None:
        now = int(time.time() * 1000)
        result = _token_expiry(  # noqa: E501
            {"expires_in": 3600}, _make_jwt(_fresh_token_payload()), action="test"
        )
        # Should be now + 3600s, within 5s tolerance
        assert result > now
        assert result < now + 3605_000

    def test_invalid_expires_in_raises(self) -> None:
        token = _make_jwt(_fresh_token_payload())
        with pytest.raises(OAuthError, match="test"):
            _token_expiry({"expires_in": "not-number"}, token, action="test")

    def test_falls_back_to_token_expiry(self) -> None:
        token = _make_jwt(_fresh_token_payload())
        result = _token_expiry({}, token, action="test")
        assert isinstance(result, int)
        assert result > int(time.time() * 1000)

    def test_no_expiry_raises(self) -> None:
        token = _make_jwt({"sub": "no-exp"})
        with pytest.raises(OAuthError, match="test"):
            _token_expiry({}, token, action="test")


# ── validate state ────────────────────────────────────────────────────────────


class TestValidateState:
    def test_matching_state(self) -> None:
        # Should not raise
        _validate_state("abc", "abc")

    def test_mismatch_raises(self) -> None:
        with pytest.raises(OAuthError, match="state"):
            _validate_state("abc", "def")

    def test_none_state_is_ok(self) -> None:
        # None state means caller didn't verify — skip
        _validate_state(None, "expected")


# ── base64 helpers ────────────────────────────────────────────────────────────


class TestBase64url:
    def test_roundtrip(self) -> None:
        original = b"hello world"
        encoded = _base64url(original)
        assert isinstance(encoded, str)
        assert "=" not in encoded  # no padding
        decoded = _base64url_decode(encoded)
        assert decoded == original

    def test_empty_bytes(self) -> None:
        assert _base64url(b"") == ""
        assert _base64url_decode("") == b""


class TestOauthHtml:
    def test_escapes_html(self) -> None:
        result = _oauth_html('Hello <world> & "friends"')
        assert "&lt;" in result
        assert "&gt;" in result
        assert "&amp;" in result
        assert "&quot;" in result
        assert "<p>" in result
        assert "</p>" in result

    def test_simple_message(self) -> None:
        result = _oauth_html("Done")
        assert "Done" in result
        assert "<p>Done</p>" in result


# ── first_query_value ────────────────────────────────────────────────────────


class TestFirstQueryValue:
    def test_returns_first_value(self) -> None:
        assert _first_query_value({"code": ["a", "b"]}, "code") == "a"

    def test_none_for_missing_key(self) -> None:
        assert _first_query_value({}, "code") is None

    def test_none_for_empty_list(self) -> None:
        assert _first_query_value({"code": []}, "code") is None

    def test_none_for_empty_string(self) -> None:
        assert _first_query_value({"code": [""]}, "code") is None


# ── exchange_openai_codex_authorization_code ─────────────────────────────────


@pytest.mark.anyio
async def test_exchange_code_success() -> None:
    """Successful code exchange returns TokenResponse."""
    resp = httpx.Response(
        200,
        json={
            "access_token": "acc_token_val",
            "refresh_token": "ref_token_val",
            "expires_in": 3600,
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await exchange_openai_codex_authorization_code("thecode", "verifier", client=client)
    assert isinstance(result, TokenResponse)
    assert result.access == "acc_token_val"
    assert result.refresh == "ref_token_val"
    assert isinstance(result.expires, int)
    assert result.expires > 0


@pytest.mark.anyio
async def test_exchange_code_http_error() -> None:
    """Non-200 response raises OAuthError."""
    resp = httpx.Response(400, text="bad request")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthError, match="exchange"):
        await exchange_openai_codex_authorization_code("c", "v", client=client)


@pytest.mark.anyio
async def test_exchange_code_non_dict_response() -> None:
    """Non-dict JSON response raises OAuthError."""
    resp = httpx.Response(200, json="just a string")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthError, match="exchange"):
        await exchange_openai_codex_authorization_code("c", "v", client=client)


@pytest.mark.anyio
async def test_exchange_code_missing_access_token() -> None:
    """Missing access_token in response raises OAuthError."""
    resp = httpx.Response(200, json={"refresh_token": "r", "expires_in": 3600})
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthError, match="exchange"):
        await exchange_openai_codex_authorization_code("c", "v", client=client)


# ── refresh_openai_codex_token ───────────────────────────────────────────────


@pytest.mark.anyio
async def test_refresh_success() -> None:
    """Successful refresh returns OAuthCredential."""
    payload = _fresh_token_payload()
    fresh_token = _make_jwt(payload)
    resp = httpx.Response(
        200,
        json={"access_token": fresh_token, "expires_in": 3600},
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await refresh_openai_codex_token("old_refresh", client=client)
    assert isinstance(result, OAuthCredential)
    assert result.access == fresh_token
    assert result.refresh == "old_refresh"  # falls back to input
    assert result.account_id == "acct_test123"


@pytest.mark.anyio
async def test_refresh_with_new_refresh_token() -> None:
    """Refresh response may include a new refresh_token."""
    payload = _fresh_token_payload()
    fresh_token = _make_jwt(payload)
    resp = httpx.Response(
        200,
        json={
            "access_token": fresh_token,
            "refresh_token": "new_refresh",
            "expires_in": 3600,
        },
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    result = await refresh_openai_codex_token("old_refresh", client=client)
    assert result.refresh == "new_refresh"


@pytest.mark.anyio
async def test_refresh_http_error() -> None:
    """Non-200 response raises OAuthError."""
    resp = httpx.Response(401, text="unauthorized")
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthError, match="refresh"):
        await refresh_openai_codex_token("r", client=client)


@pytest.mark.anyio
async def test_refresh_missing_account_id() -> None:
    """Token without account_id claim raises OAuthError."""
    token = _make_jwt({"sub": "no-account"})
    resp = httpx.Response(200, json={"access_token": token, "expires_in": 3600})
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: resp))
    with pytest.raises(OAuthError, match="account id"):
        await refresh_openai_codex_token("r", client=client)
