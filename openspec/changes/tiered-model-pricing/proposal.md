# Tiered Model Pricing

**Change**: `tiered-model-pricing`
**Status**: Spec + Design (approved)
**Storage**: `openspec/changes/tiered-model-pricing/`

---

## Intent

Some providers (MiniMax) charge different per-token rates depending on
how many input tokens the request consumes. The current flat `cost`
dict cannot express this. We need a mechanism to define cost tiers
and resolve the effective rate at runtime.

## Scope (first slice)

- MiniMax-M3 model only (1M context, tiers at 512k)
- Both MiniMax providers (`minimax` and `minimax-cn`)
- Catalog-level metadata (`ModelCatalogMetadata`) + runtime metadata
  (`ProviderModelMetadata`)

---

## Design Decisions

1. **Fallback**: when `cost_tiers` is present but no tier matches
   (theoretically shouldn't happen with an unbounded final tier),
   fall back to flat `cost`.
2. **Dual placement**: `cost_tiers` lives on BOTH
   `ModelCatalogMetadata` (catalog) and `ProviderModelMetadata`
   (runtime) — same pattern as `cost`, `headers`, etc.
3. **Resolver**: `model_cost_for_input_tokens(metadata, input_tokens)`
   returns the matching tier's cost dict or falls back to flat `cost`.
4. **Validation**: tiers must have strictly increasing
   `max_input_tokens`; the final tier must omit `max_input_tokens`
   (unbounded).

## Data Model

```python
@dataclass(frozen=True, slots=True)
class ModelCostTier:
    max_input_tokens: int | None = None  # None = unbounded (final tier only)
    input: float = 0.0
    output: float = 0.0
    cacheRead: float = 0.0
    cacheWrite: float = 0.0
```

TOML representation (inline array of inline tables):

```toml
cost_tiers = [
  { max_input_tokens = 524288, input = 0.3, output = 1.2,
    cacheRead = 0.06, cacheWrite = 0 },
  { input = 0.6, output = 2.4, cacheRead = 0.12, cacheWrite = 0 },
]
```

## MiniMax-M3 Rates

| Tier | Max Input | Input | Output | CacheRead | CacheWrite |
|------|-----------|-------|--------|-----------|------------|
| 1    | 524288    | 0.3   | 1.2    | 0.06      | 0          |
| 2    | unbounded | 0.6   | 2.4    | 0.12      | 0          |

## Files Changed

| File | Change |
|------|--------|
| `src/tau_coding/provider_catalog.py` | Add `ModelCostTier`, `cost_tiers` field, `model_cost_for_input_tokens()` |
| `src/tau_coding/catalog_loader.py` | Add `_CatalogCostTier` Pydantic model, parse `cost_tiers` |
| `src/tau_coding/provider_config.py` | Add `cost_tiers` to `ProviderModelMetadata` + `to_json()` |
| `src/tau_coding/_provider_merge.py` | Merge `cost_tiers` in model metadata and catalog round-trip |
| `src/tau_coding/_provider_parsers.py` | Parse `cost_tiers` in `_model_metadata_dict()` |
| `src/tau_coding/data/catalog.toml` | Add MiniMax-M3 with tiered rates |
| `tests/test_provider_catalog.py` | Tests for resolver + catalog loading |
| `tests/test_provider_config.py` | Tests for runtime metadata + merge |

## Implementation Tasks

1. `ModelCostTier` dataclass + `cost_tiers` field on `ModelCatalogMetadata`
2. `model_cost_for_input_tokens()` resolver
3. `_CatalogCostTier` Pydantic model + parsing in `_CatalogModelMetadata`
4. `cost_tiers` on `ProviderModelMetadata` + `to_json()` serialization
5. `cost_tiers` in `_model_metadata_dict()` parser
6. Merge/sync logic in `_merge_provider_model_metadata()` and `_catalog_model_metadata_from_provider()`
7. MiniMax-M3 entries in `catalog.toml`
8. Tests
