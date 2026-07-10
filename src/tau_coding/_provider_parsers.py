"""Primitive parser, coercion, and validation functions for provider config."""

from __future__ import annotations

from typing import Any, cast

from tau_coding.provider_catalog import ProviderApi
from tau_coding.provider_config import ProviderConfigError, ProviderModelMetadata
from tau_coding.thinking import (
    ThinkingLevel,
    ThinkingParameter,
    normalize_thinking_level,
    normalize_thinking_levels,
)


def _validate_provider_numbers(
    *,
    timeout_seconds: float,
    max_retries: int,
    max_retry_delay_seconds: float,
) -> None:
    if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ProviderConfigError("Provider timeout_seconds must be greater than 0")
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or max_retries < 0:
        raise ProviderConfigError("Provider max_retries must be 0 or greater")
    if (
        not isinstance(max_retry_delay_seconds, int | float)
        or isinstance(max_retry_delay_seconds, bool)
        or max_retry_delay_seconds < 0
    ):
        raise ProviderConfigError("Provider max_retry_delay_seconds must be 0 or greater")


def _validate_context_windows(context_windows: dict[str, int]) -> None:
    for model, context_window in context_windows.items():
        if not isinstance(model, str) or not model.strip():
            raise ProviderConfigError("Provider context_windows keys must be non-empty strings")
        if (
            not isinstance(context_window, int)
            or isinstance(context_window, bool)
            or context_window <= 0
        ):
            raise ProviderConfigError("Provider context_windows values must be positive integers")


def _validate_model_metadata(
    models: tuple[str, ...],
    model_metadata: dict[str, ProviderModelMetadata],
) -> None:
    model_names = set(models)
    for model, metadata in model_metadata.items():
        if model not in model_names:
            raise ProviderConfigError(f"Provider model_metadata key is not in models: {model}")
        if metadata.context_window is not None and metadata.context_window <= 0:
            raise ProviderConfigError("Provider model_metadata context_window must be positive")
        if metadata.max_tokens is not None and metadata.max_tokens <= 0:
            raise ProviderConfigError("Provider model_metadata max_tokens must be positive")
        if any(item not in {"text", "image"} for item in metadata.input):
            raise ProviderConfigError("Provider model_metadata input must contain text or image")
        if any(value < 0 for value in metadata.cost.values()):
            raise ProviderConfigError("Provider model_metadata cost values must be non-negative")
        _validate_json_object(metadata.compat, "Provider model_metadata compat")
        _validate_string_dict(metadata.headers, "Provider model_metadata headers")
        for level, value in metadata.thinking_level_map.items():
            normalize_thinking_level(level)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ProviderConfigError(
                    "Provider model_metadata thinking_level_map values must be strings or null"
                )


def _validate_string_dict(value: dict[str, str], field_name: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str) or not item.strip():
            raise ProviderConfigError(f"{field_name} values must be non-empty strings")


def _validate_json_object(value: dict[str, Any], field_name: str) -> None:
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"{field_name} keys must be non-empty strings")
        _validate_json_value(item, f"{field_name}.{key}")


def _validate_json_value(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | int | float | bool):
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, field_name)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProviderConfigError(f"{field_name} object keys must be strings")
            _validate_json_value(item, f"{field_name}.{key}")
        return
    raise ProviderConfigError(f"{field_name} must be JSON-compatible")


def _reject_catalog_only_legacy_metadata(
    compat: dict[str, Any],
    model_metadata: dict[str, ProviderModelMetadata],
) -> None:
    if compat or model_metadata:
        raise ProviderConfigError("OpenAI Codex legacy provider metadata is not supported")


def _validate_thinking_defaults(thinking_defaults: dict[str, ThinkingLevel]) -> None:
    for model, thinking_level in thinking_defaults.items():
        if not isinstance(model, str) or not model.strip():
            raise ProviderConfigError("Provider thinking_defaults keys must be non-empty strings")
        try:
            normalize_thinking_level(thinking_level)
        except ValueError as exc:
            raise ProviderConfigError(str(exc)) from exc


def _validate_thinking_config(
    *,
    thinking_levels: tuple[ThinkingLevel, ...] | None,
    thinking_models: tuple[str, ...],
    thinking_default: ThinkingLevel | None,
    thinking_parameter: ThinkingParameter | None,
) -> None:
    if thinking_levels is None:
        if thinking_models or thinking_default is not None or thinking_parameter is not None:
            raise ProviderConfigError(
                "Provider thinking_levels must be set before thinking metadata"
            )
        return
    try:
        normalized = normalize_thinking_levels(thinking_levels)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc
    if normalized != thinking_levels:
        raise ProviderConfigError("Provider thinking_levels must be normalized")
    if any(not isinstance(model, str) or not model.strip() for model in thinking_models):
        raise ProviderConfigError("Provider thinking_models must contain non-empty strings")
    if thinking_default is not None and thinking_default not in thinking_levels:
        raise ProviderConfigError("Provider thinking_default must be in thinking_levels")
    if thinking_parameter not in {
        None,
        "reasoning_effort",
        "reasoning.effort",
        "anthropic.thinking",
    }:
        raise ProviderConfigError(
            "Provider thinking_parameter must be reasoning_effort, reasoning.effort, "
            "or anthropic.thinking"
        )


def _reject_unimplemented_thinking_config(
    *,
    provider_type: str,
    thinking_levels: tuple[ThinkingLevel, ...] | None,
) -> None:
    if thinking_levels is not None:
        raise ProviderConfigError(f"{provider_type} thinking controls are not implemented yet")


def _optional_provider_api(value: object, field_name: str) -> ProviderApi | None:
    if value is None:
        return None
    if value in {
        "openai-completions",
        "openai-responses",
        "anthropic-messages",
        "openai-codex-responses",
        "google-generative-ai",
        "mistral-conversations",
    }:
        return cast(ProviderApi, value)
    raise ProviderConfigError(f"Provider field has unsupported API: {field_name}")


def _optional_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"Provider field must be a non-empty string: {field_name}")
    return value.strip()


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderConfigError(f"Provider field must be a non-empty string: {field_name}")
    return value.strip()


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ProviderConfigError(f"Provider field must be a non-empty string list: {field_name}")
    items = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(items) != len(value):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    return items


def _optional_string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    items = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(items) != len(value):
        raise ProviderConfigError(f"Provider field must be a string list: {field_name}")
    return items


def _optional_thinking_levels(
    value: object,
    field_name: str,
) -> tuple[ThinkingLevel, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ProviderConfigError(f"Provider field must be a thinking mode list: {field_name}")
    try:
        return normalize_thinking_levels(value)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc


def _optional_thinking_level(value: object, field_name: str) -> ThinkingLevel | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
    try:
        return normalize_thinking_level(value)
    except ValueError as exc:
        raise ProviderConfigError(str(exc)) from exc


def _optional_thinking_parameter(
    value: object,
    field_name: str,
) -> ThinkingParameter | None:
    if value is None:
        return None
    if value == "reasoning_effort":
        return "reasoning_effort"
    if value == "reasoning.effort":
        return "reasoning.effort"
    if value == "anthropic.thinking":
        return "anthropic.thinking"
    raise ProviderConfigError(
        f"Provider field must be reasoning_effort, reasoning.effort, "
        f"or anthropic.thinking: {field_name}"
    )


def _string_dict(value: object, field_name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
    items: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
        if not isinstance(item, str) or not item.strip():
            raise ProviderConfigError(f"Provider field must be a string object: {field_name}")
        items[key.strip()] = item.strip()
    return items


def _json_dict(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    items: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must have string keys: {field_name}")
        _validate_json_value(item, f"{field_name}.{key}")
        items[key.strip()] = item
    return items


def _model_metadata_dict(
    value: object,
    models: tuple[str, ...],
    field_name: str,
) -> dict[str, ProviderModelMetadata]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    model_names = set(models)
    items: dict[str, ProviderModelMetadata] = {}
    for key, item in value.items():
        model = _string(key, field_name)
        if model not in model_names:
            raise ProviderConfigError(f"Provider model_metadata key is not in models: {model}")
        if not isinstance(item, dict):
            raise ProviderConfigError(
                f"Provider model_metadata entries must be objects: {field_name}"
            )
        items[model] = ProviderModelMetadata(
            name=_optional_string(item.get("name"), f"{field_name}.{model}.name"),
            api=_optional_provider_api(item.get("api"), f"{field_name}.{model}.api"),
            base_url=_optional_string(item.get("base_url"), f"{field_name}.{model}.base_url"),
            reasoning=_optional_bool(item.get("reasoning"), f"{field_name}.{model}.reasoning"),
            input=_optional_string_tuple(item.get("input"), f"{field_name}.{model}.input"),
            cost=_float_dict(item.get("cost", {}), f"{field_name}.{model}.cost"),
            context_window=_optional_positive_int(
                item.get("context_window"), f"{field_name}.{model}.context_window"
            ),
            max_tokens=_optional_positive_int(
                item.get("max_tokens"), f"{field_name}.{model}.max_tokens"
            ),
            headers=_string_dict(item.get("headers", {}), f"{field_name}.{model}.headers"),
            compat=_json_dict(item.get("compat", {}), f"{field_name}.{model}.compat"),
            thinking_level_map=_thinking_level_map_dict(
                item.get("thinking_level_map", {}),
                f"{field_name}.{model}.thinking_level_map",
            ),
        )
    return items


def _thinking_level_map_dict(
    value: object,
    field_name: str,
) -> dict[ThinkingLevel, str | None]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an object: {field_name}")
    items: dict[ThinkingLevel, str | None] = {}
    for key, item in value.items():
        level = _optional_thinking_level(key, field_name)
        if level is None:
            raise ProviderConfigError(f"Provider field must be a thinking mode: {field_name}")
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise ProviderConfigError(
                f"Provider field values must be strings or null: {field_name}"
            )
        items[level] = item.strip() if isinstance(item, str) else None
    return items


def _float_dict(value: object, field_name: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be a number object: {field_name}")
    items: dict[str, float] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be a number object: {field_name}")
        if not isinstance(item, int | float) or isinstance(item, bool) or item < 0:
            raise ProviderConfigError(f"Provider field values must be non-negative: {field_name}")
        items[key.strip()] = float(item)
    return items


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a boolean: {field_name}")
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ProviderConfigError(f"Provider field must be a positive integer: {field_name}")
    return value


def _context_window_dict(value: object, field_name: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ProviderConfigError(f"Provider field must be an integer object: {field_name}")
    items: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ProviderConfigError(f"Provider field must be an integer object: {field_name}")
        if not isinstance(item, int) or isinstance(item, bool) or item <= 0:
            raise ProviderConfigError(
                f"Provider field values must be positive integers: {field_name}"
            )
        items[key.strip()] = item
    return items


def _positive_float(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a positive number: {field_name}")
    converted = float(value)
    if converted <= 0:
        raise ProviderConfigError(f"Provider field must be greater than 0: {field_name}")
    return converted


def _non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a non-negative integer: {field_name}")
    if value < 0:
        raise ProviderConfigError(f"Provider field must be 0 or greater: {field_name}")
    return value


def _non_negative_float(value: object, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ProviderConfigError(f"Provider field must be a non-negative number: {field_name}")
    converted = float(value)
    if converted < 0:
        raise ProviderConfigError(f"Provider field must be 0 or greater: {field_name}")
    return converted
