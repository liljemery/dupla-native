# APS Token Refresh Hardening Sprint — Summary

**Goal:** Make long-running Autodesk Model Derivative polls survive token expiry without
breaking any other pipeline behaviour. This is the final APS-only hardening step before
returning to core product work (quantities → budget → workbook).

---

## What changed

### `aps_integration/model_derivative.py`

| Area | Change |
|------|--------|
| `_request_with_token_refresh` | Reusable helper that catches HTTP 401, calls `get_aps_token()`, retries once, and returns the response. Used by every public API function. |
| `_coerce_token_state` | Normalises `token` (plain string or dict) into a mutable `{"access_token": ..., "refresh_count": 0}` dict. When a dict is passed in, mutations are visible to the caller — this is how the refreshed token propagates. |
| `get_manifest` / `translate_to_svf2` / `get_model_views` / `get_all_properties` / `query_specific_properties` | All route through `_request_with_token_refresh`. |
| `wait_for_translation` | Receives and holds the shared `token_state` dict; any refresh inside a manifest poll is visible to the next poll iteration and to all subsequent calls in `extract_dwg_data`. |
| `extract_dwg_data` | Single shared `token_state` dict flows through the entire pipeline (translate → poll → views → properties → salvage). Token refresh count is recorded in the returned dict as `token_refresh_count`. |
| `_build_failed_translation_message` | Now includes `object_name` and `token_refresh_happened` in the error string, giving operators all the context needed to diagnose failures. |
| `extract_dwg_data` docstring | Added a short example showing the mutable `token_state` pattern. |

### `tests/test_model_derivative.py`

| Test | Covers |
|------|--------|
| `test_wait_for_translation_refreshes_token_on_401_and_reuses_it` | 401 during manifest polling → token refresh → polling continues with fresh token |
| `test_get_all_properties_refreshes_token_on_401_then_succeeds` | 401 during property fetch → token refresh → data returned |
| `test_extract_dwg_data_refreshed_token_reused_across_later_calls` | *(new)* Token refreshed in initial manifest fetch is the same token used by later property-fetch calls via the shared `token_state` dict |
| `test_extract_dwg_data_failed_error_includes_manifest_and_salvage_flags` | Extended to assert `object_name` and `token_refresh_happened` appear in the error message |
| `test_extract_dwg_data_salvages_failed_manifest_with_property_database` | No regression: salvage path and failed-manifest grace polls still work |

---

## Token refresh flow (one-liner summary)

```
expired token → 401 response → get_aps_token() → mutate token_state dict
→ retry succeeds → all remaining calls in the same run use the fresh token
```

```python
# Passing a dict lets the caller observe the refresh after the call:
token_state = {"access_token": get_aps_token(), "refresh_count": 0}
result = extract_dwg_data(token_state, bucket_key, object_name)
# result["token_refresh_count"] > 0  →  at least one refresh happened
# token_state["access_token"]        →  holds the most recent valid token
```

---

## What was NOT changed

- Quantifier agent, rules engine, budget composer, vision agent — untouched.
- 2D-only default translation — preserved.
- Failed-manifest grace polls — preserved.
- Salvage path (PropertyDatabase fallback) — preserved.
- Unique object naming / sticky URN behaviour — preserved.
- `dupla_run_full_analysis_local.py` — no changes required; passing a plain string token
  already works because `_coerce_token_state` handles both forms.

---

## Status

APS integration is stable. Long polls survive token expiry. Salvage path still works.
**Next step: return to core product pipeline (quantities → budget → workbook).**
