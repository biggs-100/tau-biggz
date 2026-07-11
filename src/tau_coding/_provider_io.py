"""Provider settings filesystem I/O."""

from __future__ import annotations

from contextlib import suppress
from json import dumps, loads
from pathlib import Path
from shutil import copy2
from tempfile import NamedTemporaryFile

from tau_coding._provider_deserialize import provider_settings_from_json
from tau_coding._provider_merge import (
    _effective_provider_configs,
    _save_provider_definitions_to_catalog,
    _with_builtin_catalog_models,
)
from tau_coding.paths import TauPaths
from tau_coding.provider_config import (
    ProviderConfigError,
    ProviderSettings,
)


def provider_settings_path(paths: TauPaths | None = None) -> Path:
    """Return the durable provider settings path."""
    return (paths or TauPaths()).home / "providers.json"


def load_provider_settings(paths: TauPaths | None = None) -> ProviderSettings:
    """Load durable provider settings, falling back to env-compatible defaults."""
    resolved_paths = paths or TauPaths()
    path = provider_settings_path(resolved_paths)
    if not path.exists():
        return ProviderSettings(providers=_effective_provider_configs(resolved_paths))
    raw = loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProviderConfigError("Provider settings must be a JSON object")
    settings = provider_settings_from_json(raw, paths=resolved_paths)
    return _with_builtin_catalog_models(settings, paths=resolved_paths)


def save_provider_settings(settings: ProviderSettings, paths: TauPaths | None = None) -> Path:
    """Write durable provider preferences and return the path."""
    resolved_paths = paths or TauPaths()
    _save_provider_definitions_to_catalog(settings, paths=resolved_paths)
    path = provider_settings_path(resolved_paths)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with suppress(OSError):
            copy2(path, path.with_suffix(path.suffix + ".bak"))
    _atomic_write_text(path, dumps(settings.to_json(), indent=2, sort_keys=True) + "\n")
    return path


def _load_provider_settings_for_write(
    paths: TauPaths | None,
    *,
    fallback_settings: ProviderSettings | None = None,
) -> ProviderSettings:
    """Load the latest on-disk settings, falling back only when no file exists."""
    # Import through provider_config so external monkeypatching
    # (e.g. test mocks) targeting provider_config.load_provider_settings takes effect.
    from tau_coding.provider_config import load_provider_settings as _reload

    resolved_paths = paths or TauPaths()
    if provider_settings_path(resolved_paths).exists():
        return _reload(resolved_paths)
    if fallback_settings is not None:
        return fallback_settings
    return _reload(resolved_paths)


def _atomic_write_text(path: Path, text: str) -> None:
    """Write text through a sibling temp file and atomically replace the target."""
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            dir=path.parent,
            encoding="utf-8",
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(text)
            temp_file.flush()
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            with suppress(OSError):
                temp_path.unlink()
        raise
