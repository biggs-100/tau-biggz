import json
import sys
from stat import S_IMODE

import pytest

from tau_coding.credentials import CredentialStoreError, FileCredentialStore, OAuthCredential


def test_file_credential_store_round_trips_and_sets_private_permissions(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)

    store.set("openai", "test-key")

    assert store.get("openai") == "test-key"
    # Windows doesn't support Unix rwx permissions; just verify the file is not world-readable
    if sys.platform != "win32":
        assert S_IMODE(path.stat().st_mode) == 0o600


def test_file_credential_store_deletes_key(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")
    store.set("openai", "test-key")

    store.delete("openai")

    assert store.get("openai") is None


def test_file_credential_store_rejects_empty_values(tmp_path) -> None:
    store = FileCredentialStore(tmp_path / "credentials.json")

    with pytest.raises(CredentialStoreError, match="must not be empty"):
        store.set("openai", "")


def test_file_credential_store_round_trips_oauth_credentials(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)
    credential = OAuthCredential(
        access="access-token",
        refresh="refresh-token",
        expires=123456,
        account_id="account-1",
    )

    store.set_oauth("openai-codex", credential)

    assert store.get("openai-codex") is None
    assert store.get_oauth("openai-codex") == credential
    assert '"type": "oauth"' in path.read_text(encoding="utf-8")


def test_oauth_credential_with_metadata(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    store = FileCredentialStore(path)
    credential = OAuthCredential(
        access="a",
        refresh="r",
        expires=123456,
        account_id="acct-1",
        metadata={"provider": "anthropic-oauth", "version": 1},
    )

    store.set_oauth("anthropic-oauth", credential)

    loaded = store.get_oauth("anthropic-oauth")
    assert loaded is not None
    assert loaded.metadata == {"provider": "anthropic-oauth", "version": 1}


def test_oauth_credential_backward_compat_no_metadata(tmp_path) -> None:
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps({
            "test-provider": {
                "type": "oauth",
                "access": "a",
                "refresh": "r",
                "expires": 123456,
                "account_id": "acct-1",
            }
        })
    )
    store = FileCredentialStore(path)
    loaded = store.get_oauth("test-provider")
    assert loaded is not None
    assert loaded.metadata == {}
    assert loaded.access == "a"
