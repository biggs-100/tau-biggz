"""Tests for tau models sync.

Covers merge logic, cache lifecycle, offline fallback, and HTTP edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from tau_coding.models_sync import (
    SyncResult,
    _merge_external_data,
    _merge_model_data,
    _read_cache,
    _resolve_provider_name,
    _write_cache,
    sync_models,
)
from tau_coding.provider_config import (
    AnthropicProviderConfig,
    OpenAICodexProviderConfig,
    OpenAICompatibleProviderConfig,
    ProviderModelMetadata,
    ProviderSettings,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "models.dev.api.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_fixture() -> dict[str, Any]:
    """Load the truncated models.dev API snapshot."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _make_openai_provider() -> OpenAICompatibleProviderConfig:
    """A realistic OpenAI provider with context_windows and model_metadata."""
    return OpenAICompatibleProviderConfig(
        name="openai",
        models=("gpt-5.4", "gpt-5.4-mini", "o4-mini"),
        default_model="gpt-5.4",
        context_windows={"gpt-5.4": 128000, "gpt-5.4-mini": 128000, "o4-mini": 100000},
        model_metadata={
            "gpt-5.4": ProviderModelMetadata(
                name="gpt-5.4",
                context_window=128000,
                reasoning=False,
                max_tokens=4096,
            ),
        },
    )


def _make_anthropic_provider() -> AnthropicProviderConfig:
    """A realistic Anthropic provider."""
    return AnthropicProviderConfig(
        name="anthropic",
        models=("claude-sonnet-4-6", "claude-haiku-4-5"),
        default_model="claude-sonnet-4-6",
        context_windows={"claude-sonnet-4-6": 200000, "claude-haiku-4-5": 200000},
        model_metadata={
            "claude-sonnet-4-6": ProviderModelMetadata(
                name="claude-sonnet-4-6",
                context_window=200000,
                reasoning=True,
                max_tokens=8192,
            ),
        },
    )


def _make_codex_provider() -> OpenAICodexProviderConfig:
    """A codex provider (no model_metadata field)."""
    return OpenAICodexProviderConfig(
        name="openai-codex",
        models=("gpt-5.5", "gpt-5.4"),
        default_model="gpt-5.5",
        context_windows={"gpt-5.5": 200000, "gpt-5.4": 128000},
    )


# ===================================================================
# Task 8: Provider Name Resolution Tests
# ===================================================================


class TestResolveProviderName:
    """_resolve_provider_name: exact, mapped, case-insensitive, no-match."""

    def test_exact_match(self):
        """Exact match returns the key as-is."""
        data = {"openai": {}, "anthropic": {}}
        assert _resolve_provider_name("openai", data) == "openai"

    def test_mapped_reverse(self):
        """'xai' maps to 'x-ai' via _PROVIDER_NAME_MAP."""
        data = {"x-ai": {}, "openai": {}}
        assert _resolve_provider_name("xai", data) == "x-ai"

    def test_case_insensitive(self):
        """Case-insensitive fallback matches 'OpenAI' to 'openai'."""
        data = {"openai": {}, "anthropic": {}}
        assert _resolve_provider_name("OpenAI", data) == "openai"

    def test_no_match(self):
        """Unknown provider returns None."""
        data = {"openai": {}}
        assert _resolve_provider_name("unknown-provider", data) is None

    def test_identity_mapped(self):
        """'opencode-go' maps to itself (identity in _PROVIDER_NAME_MAP)."""
        data = {"opencode-go": {}}
        assert _resolve_provider_name("opencode-go", data) == "opencode-go"

    def test_fixture_mapping(self):
        """Fixture-based integration: xai resolves to x-ai."""
        data = _load_fixture()
        assert _resolve_provider_name("xai", data) == "x-ai"

    def test_fixture_exact(self):
        """Fixture-based integration: openai resolves to openai."""
        data = _load_fixture()
        assert _resolve_provider_name("openai", data) == "openai"


# ===================================================================
# Task 8: _merge_model_data Tests
# ===================================================================


class TestMergeModelData:
    """_merge_model_data: context_windows, model_metadata, type validation."""

    def test_updates_context_window(self):
        """External context value updates context_windows."""
        provider = _make_openai_provider()
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": 2000000}},
            update_model_metadata=True,
        )
        assert result.context_windows["gpt-5.4"] == 2000000
        # Verify unchanged models are preserved
        assert result.context_windows["gpt-5.4-mini"] == 128000

    def test_updates_model_metadata(self):
        """All three external fields update model_metadata."""
        provider = _make_openai_provider()
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": 2000000, "output": 131072}, "reasoning": True},
            update_model_metadata=True,
        )
        meta = result.model_metadata["gpt-5.4"]
        assert meta.context_window == 2000000
        assert meta.reasoning is True
        assert meta.max_tokens == 131072

    def test_creates_new_metadata_entry(self):
        """Model in provider.models but not in model_metadata gets created."""
        provider = _make_openai_provider()
        # o4-mini is in models but not in model_metadata for the default provider
        assert "o4-mini" not in provider.model_metadata
        result = _merge_model_data(
            provider,
            "o4-mini",
            {"limit": {"context": 1000000, "output": 65536}, "reasoning": True},
            update_model_metadata=True,
        )
        assert "o4-mini" in result.model_metadata
        meta = result.model_metadata["o4-mini"]
        assert meta.context_window == 1000000
        assert meta.reasoning is True
        assert meta.max_tokens == 65536
        assert meta.name == "o4-mini"

    def test_identity_when_no_match(self):
        """Returns same object when no external data matches."""
        provider = _make_openai_provider()
        result = _merge_model_data(
            provider,
            "nonexistent-model",
            {"limit": {"context": 100000}},
            update_model_metadata=True,
        )
        assert result is provider  # identity check

    def test_codex_only_context_windows(self):
        """OpenAICodexProviderConfig updates only context_windows."""
        provider = _make_codex_provider()
        result = _merge_model_data(
            provider,
            "gpt-5.5",
            {"limit": {"context": 200000, "output": 99999}, "reasoning": True},
            update_model_metadata=False,
        )
        assert result.context_windows["gpt-5.5"] == 200000
        # No model_metadata attribute on OpenAICodexProviderConfig
        assert not hasattr(result, "model_metadata")

    def test_type_validation_skips_invalid(self):
        """Invalid types are silently skipped, valid fields still merged."""
        provider = _make_openai_provider()
        # Reasoning="yes" (not bool), context="not-a-number" (not int)
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": "not-a-number", "output": 99999}, "reasoning": "yes"},
            update_model_metadata=True,
        )
        # max_output is valid int > 0, so max_tokens should be updated
        meta = result.model_metadata["gpt-5.4"]
        assert meta.max_tokens == 99999
        # context_window and reasoning should keep their original values
        assert meta.context_window == 128000
        assert meta.reasoning is False
        # context_windows should NOT be updated since context is not a valid int
        assert result.context_windows["gpt-5.4"] == 128000

    def test_identity_when_no_valid_data(self):
        """When all external data is invalid, returns same object."""
        provider = _make_openai_provider()
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": -1, "output": 0}, "reasoning": "yes"},
            update_model_metadata=True,
        )
        assert result is provider

    def test_partial_external_data(self):
        """Missing fields leave existing values intact."""
        provider = _make_openai_provider()
        # Only context provided, no reasoning or max_output
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": 2000000}},
            update_model_metadata=True,
        )
        meta = result.model_metadata["gpt-5.4"]
        assert meta.context_window == 2000000
        assert meta.reasoning is False  # unchanged
        assert meta.max_tokens == 4096  # unchanged
        assert result.context_windows["gpt-5.4"] == 2000000

    def test_null_reasoning_skipped(self):
        """reasoning=null (None) is not a bool, so it should be skipped."""
        provider = _make_openai_provider()
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": 2000000, "output": 131072}, "reasoning": None},
            update_model_metadata=True,
        )
        meta = result.model_metadata["gpt-5.4"]
        assert meta.context_window == 2000000
        assert meta.reasoning is False  # unchanged (None is not bool)
        assert meta.max_tokens == 131072

    def test_identity_for_unchanged_values(self):
        """When external values match current values, returns same object."""
        provider = _make_openai_provider()
        # Same values as existing
        result = _merge_model_data(
            provider,
            "gpt-5.4",
            {"limit": {"context": 128000, "output": 4096}, "reasoning": False},
            update_model_metadata=True,
        )
        assert result is provider  # identity — no changes


# ===================================================================
# Task 8: _merge_external_data Snapshot Tests
# ===================================================================


class TestMergeExternalData:
    """_merge_external_data with fixture data produces correct counts."""

    def test_snapshot_merge_full(self):
        """Full fixture merge produces correct counts and values."""
        fixture = _load_fixture()
        settings = ProviderSettings(
            providers=(
                _make_openai_provider(),
                _make_anthropic_provider(),
            )
        )

        result, updated = _merge_external_data(settings, fixture)

        assert result.success
        assert result.providers_updated == 2
        assert result.models_updated >= 4
        assert result.source == "api"

        # Verify openai gpt-5.4 got updated
        openai = updated.providers[0]
        assert openai.context_windows["gpt-5.4"] == 2000000
        meta = openai.model_metadata["gpt-5.4"]
        assert meta.context_window == 2000000
        assert meta.reasoning is True
        assert meta.max_tokens == 131072

        # Verify anthropic claude-haiku-4-5 got updated
        anthro = updated.providers[1]
        assert anthro.context_windows["claude-haiku-4-5"] == 200000
        meta2 = anthro.model_metadata["claude-haiku-4-5"]
        assert meta2.context_window == 200000
        assert meta2.reasoning is False  # explicitly false in fixture
        assert meta2.max_tokens == 4096

    def test_no_providers_match(self):
        """When no provider names match external data, nothing changes."""
        settings = ProviderSettings(
            providers=(
                OpenAICompatibleProviderConfig(
                    name="custom-provider",
                    models=("model-x",),
                    default_model="model-x",
                ),
            )
        )
        fixture = _load_fixture()
        result, updated = _merge_external_data(settings, fixture)
        assert result.providers_updated == 0
        assert result.models_updated == 0
        assert updated.providers[0] is settings.providers[0]

    def test_codex_provider_skips_model_metadata(self):
        """OpenAICodexProviderConfig only gets context_windows updates."""
        codex = _make_codex_provider()
        settings = ProviderSettings(providers=(codex,))
        fixture = {
            "openai-codex": {
                "models": {
                    "gpt-5.5": {"limit": {"context": 999999, "output": 123456}, "reasoning": True}
                }
            }
        }

        result, updated = _merge_external_data(settings, fixture)

        assert result.providers_updated == 1
        updated_codex = updated.providers[0]
        assert updated_codex.context_windows["gpt-5.5"] == 999999
        # OpenAICodexProviderConfig has no model_metadata
        assert not hasattr(updated_codex, "model_metadata")
        assert isinstance(updated_codex, OpenAICodexProviderConfig)


# ===================================================================
# Task 9: Cache Tests
# ===================================================================


class TestCacheRoundTrip:
    """_write_cache / _read_cache lifecycle."""

    def test_round_trip(self, tmp_path: Path):
        """Write then read preserves all fields."""
        cache_path = tmp_path / "cache.json"
        resp = httpx.Response(
            200,
            json={},
            headers={
                "etag": '"abc123"',
                "last-modified": "Wed, 08 Jul 2026 12:00:00 GMT",
            },
        )
        data = {"openai": {"models": {"gpt-4": {"limit": {"context": 100000}}}}}

        _write_cache(cache_path, resp, data)
        assert cache_path.exists()

        result = _read_cache(cache_path)
        assert result is not None
        assert result["etag"] == '"abc123"'
        assert result["last_modified"] == "Wed, 08 Jul 2026 12:00:00 GMT"
        assert result["data"] == data
        assert "cached_at" in result

    def test_missing_file_returns_none(self, tmp_path: Path):
        """Nonexistent cache path returns None."""
        cache_path = tmp_path / "nonexistent.json"
        assert _read_cache(cache_path) is None

    def test_corrupt_json_deleted(self, tmp_path: Path):
        """Invalid JSON causes file deletion and returns None."""
        cache_path = tmp_path / "cache.json"
        cache_path.write_text("not valid json", encoding="utf-8")

        result = _read_cache(cache_path)
        assert result is None
        assert not cache_path.exists()  # deleted

    def test_invalid_schema_deleted(self, tmp_path: Path):
        """Valid JSON but missing 'data' key causes deletion and returns None."""
        cache_path = tmp_path / "cache.json"
        cache_path.write_text(json.dumps({"etag": '"x"', "cached_at": "now"}), encoding="utf-8")

        result = _read_cache(cache_path)
        assert result is None
        assert not cache_path.exists()

    def test_cache_not_written_on_304(self, tmp_path: Path):
        """304 response does NOT write cache."""
        cache_path = tmp_path / "cache.json"
        settings = ProviderSettings(
            providers=(
                OpenAICompatibleProviderConfig(name="test", models=("m1",), default_model="m1"),
            )
        )

        def handler_304(request: httpx.Request) -> httpx.Response:
            return httpx.Response(304)

        with httpx.Client(transport=httpx.MockTransport(handler_304)) as client:
            # Pre-write a cache so it takes the conditional path
            _write_cache(
                cache_path,
                httpx.Response(200, json={}, headers={"etag": '"old"'}),
                {"test": {"models": {"m1": {"limit": {"context": 1000}}}}},
            )

            old_mtime = cache_path.stat().st_mtime_ns
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert result.success
        assert result.providers_updated == 1
        assert result.models_updated == 1
        assert result.source == "api"
        # Cache should NOT have been re-written (mtime unchanged)
        assert cache_path.stat().st_mtime_ns == old_mtime

    def test_etag_persistence(self, tmp_path: Path):
        """ETag from first request is stored and sent in second request."""
        cache_path = tmp_path / "cache.json"
        settings = ProviderSettings(providers=())

        etag_sent: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            etag_sent.append(request.headers.get("If-None-Match"))
            if request.headers.get("If-None-Match") == '"abc123"':
                return httpx.Response(304)
            return httpx.Response(
                200,
                json={"test": {}},
                headers={"etag": '"abc123"', "last-modified": "Wed, 08 Jul 2026 12:00:00 GMT"},
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            # First call — no cache, should get 200 and write cache
            result1, _ = sync_models(settings, http_client=client, cache_path=cache_path)
            assert result1.success

        # Now cache has etag
        cached = _read_cache(cache_path)
        assert cached is not None
        assert cached["etag"] == '"abc123"'

        # Second call — should send If-None-Match
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result2, _ = sync_models(settings, http_client=client, cache_path=cache_path)
            assert result2.success
            assert result2.providers_updated == 0  # 304 → no changes

        assert '"abc123"' in (etag_sent or [])


# ===================================================================
# Task 9: Cache Lifecycle with merge scenarios
# ===================================================================


class TestCacheMergeIntegration:
    """Integration: cache + merge produce correct values."""

    def test_200_parses_and_merges(self, tmp_path: Path):
        """200 response with fixture data writes cache and merges correctly."""
        cache_path = tmp_path / "cache.json"
        fixture = _load_fixture()
        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_200(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=fixture, headers={"etag": '"test-etag"'})

        # No pre-existing cache — unconditional fetch
        with httpx.Client(transport=httpx.MockTransport(handler_200)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert result.success
        assert result.source == "api"
        assert result.providers_updated == 1
        assert result.models_updated >= 1

        # Cache should have been written
        cached = _read_cache(cache_path)
        assert cached is not None
        assert cached["etag"] == '"test-etag"'
        assert cached["data"] == fixture

        # Merged values correct
        openai = updated.providers[0]
        assert openai.context_windows["gpt-5.4"] == 2000000


# ===================================================================
# Task 10: Offline / Error Fallback Tests
# ===================================================================


class TestOfflineFallback:
    """Network errors and parse errors with/without cache."""

    def test_offline_fallback_with_cache(self, tmp_path: Path):
        """Network error + cache → source='cache', success=True, merges happen."""
        cache_path = tmp_path / "cache.json"
        fixture = _load_fixture()

        # Pre-write cache
        resp = httpx.Response(200, json=fixture, headers={"etag": '"cached"'})
        _write_cache(cache_path, resp, fixture)

        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        with httpx.Client(transport=httpx.MockTransport(handler_error)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert result.success
        assert result.source == "cache"
        assert result.providers_updated == 1

        openai = updated.providers[0]
        assert openai.context_windows["gpt-5.4"] == 2000000  # merged from cache

    def test_offline_fallback_no_cache(self, tmp_path: Path):
        """Network error + no cache → success=False, source='none'."""
        cache_path = tmp_path / "cache.json"
        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_error(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        with httpx.Client(transport=httpx.MockTransport(handler_error)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert not result.success
        assert result.source == "none"
        assert result.error is not None
        # Updated settings should be the original (unchanged)
        assert updated.providers[0] is settings.providers[0]

    def test_parse_error_fallback_with_cache(self, tmp_path: Path):
        """Parse error + cache → source='cache'."""
        cache_path = tmp_path / "cache.json"
        fixture = _load_fixture()

        # Pre-write cache with fixture
        resp = httpx.Response(200, json=fixture, headers={"etag": '"cached"'})
        _write_cache(cache_path, resp, fixture)

        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_bad_json(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not valid json at all")

        with httpx.Client(transport=httpx.MockTransport(handler_bad_json)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert result.success
        assert result.source == "cache"
        assert result.providers_updated == 1

        openai = updated.providers[0]
        assert openai.context_windows["gpt-5.4"] == 2000000  # merged from cache

    def test_parse_error_no_cache(self, tmp_path: Path):
        """Parse error + no cache → success=False, source='none'."""
        cache_path = tmp_path / "cache.json"
        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_bad_json(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="{broken")

        with httpx.Client(transport=httpx.MockTransport(handler_bad_json)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert not result.success
        assert result.source == "none"
        assert "parse" in (result.error or "").lower() or "JSON" in (result.error or "")

    def test_non_200_fallback_with_cache(self, tmp_path: Path):
        """Non-200/304 status + cache → source='cache'."""
        cache_path = tmp_path / "cache.json"
        fixture = _load_fixture()

        resp = httpx.Response(200, json=fixture, headers={"etag": '"cached"'})
        _write_cache(cache_path, resp, fixture)

        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_500(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        with httpx.Client(transport=httpx.MockTransport(handler_500)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert result.success
        assert result.source == "cache"
        assert result.providers_updated == 1

    def test_non_200_no_cache(self, tmp_path: Path):
        """Non-200/304 status + no cache → success=False."""
        cache_path = tmp_path / "cache.json"
        settings = ProviderSettings(providers=(_make_openai_provider(),))

        def handler_500(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="Internal Server Error")

        with httpx.Client(transport=httpx.MockTransport(handler_500)) as client:
            result, updated = sync_models(settings, http_client=client, cache_path=cache_path)

        assert not result.success
        assert result.source == "none"

    def test_sync_models_injected_client_not_closed(self, tmp_path: Path):
        """Injected http_client is NOT closed by sync_models."""
        cache_path = tmp_path / "cache.json"

        def handler_200(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"test": {"models": {"m1": {"limit": {"context": 1000}}}}}
            )

        settings = ProviderSettings(
            providers=(
                OpenAICompatibleProviderConfig(name="test", models=("m1",), default_model="m1"),
            )
        )

        client = httpx.Client(transport=httpx.MockTransport(handler_200))
        result, _ = sync_models(settings, http_client=client, cache_path=cache_path)
        # Client should still be open
        assert not client.is_closed
        client.close()


# ===================================================================
# Task 8: SyncResult frozen dataclass
# ===================================================================


class TestSyncResult:
    """SyncResult is frozen and behaves correctly."""

    def test_frozen(self):
        """SyncResult instances cannot be mutated."""
        r = SyncResult(success=True, providers_updated=0, models_updated=0, source="api")
        with pytest.raises(AttributeError):
            r.success = False  # type: ignore[misc]

    def test_default_error_none(self):
        """error defaults to None."""
        r = SyncResult(success=True, providers_updated=0, models_updated=0, source="api")
        assert r.error is None
