# Spec: Google Gemini Provider Hardening

## Overview

Harden the `GoogleGenerativeAIProvider` (src/tau_ai/google.py) to production quality. This addresses five gaps: test coverage, xhigh thinking level support, thoughtSignature round-trip for multi-turn tool calls, schema sanitization, and thinking-text preservation in AssistantMessage.

## Requirements

### 1. Tests — REQ-TEST

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-TEST-1 | A dedicated `tests/test_google_provider.py` file MUST exist with all Google-provider tests. | MUST |
| REQ-TEST-2 | The test file MUST achieve >= 85% line coverage for `src/tau_ai/google.py`. | MUST |
| REQ-TEST-3 | Thinking streaming MUST be tested: a `thinking: true` text part in a Gemini SSE response MUST emit `ProviderThinkingDeltaEvent` events. | MUST |
| REQ-TEST-4 | Non-thinking text parts MUST emit `ProviderTextDeltaEvent` events. | MUST |
| REQ-TEST-5 | A mixed stream with both thinking and non-thinking parts MUST emit the correct interleaved event sequence. | MUST |
| REQ-TEST-6 | Tool call streaming MUST be tested: a `functionCall` part in the SSE stream MUST emit a `ProviderToolCallEvent` with a correctly populated `ToolCall`. | MUST |
| REQ-TEST-7 | Multiple tool calls in a single response MUST each produce their own `ProviderToolCallEvent`. | MUST |
| REQ-TEST-8 | A tool call with no `id` field MUST fall back to a generated default `tool-call-N` id. | MUST |
| REQ-TEST-9 | The final `ProviderResponseEndEvent` MUST carry the `AssistantMessage` with the accumulated content and tool calls. | MUST |
| REQ-TEST-10 | HTTP errors (4xx, 5xx) MUST be tested: non-retryable errors MUST yield `ProviderErrorEvent`. | MUST |
| REQ-TEST-11 | Retryable HTTP errors (408, 409, 425, 429, >=500) MUST yield `ProviderRetryEvent` and retry up to `max_retries`. | MUST |
| REQ-TEST-12 | When all retries are exhausted, the provider MUST yield `ProviderErrorEvent`. | MUST |
| REQ-TEST-13 | Network errors (httpx.HTTPError without emitted content) MUST yield `ProviderRetryEvent` and retry. | MUST |
| REQ-TEST-14 | A network error after content was already emitted MUST NOT retry — it MUST yield `ProviderErrorEvent` immediately. | MUST |
| REQ-TEST-15 | Thinking levels MUST be tested: `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`, and `xhigh` as `reasoning_effort` MUST produce correct `thinkingConfig` in the payload. | MUST |
| REQ-TEST-16 | `reasoning_effort=None` MUST omit `thinkingConfig` from the payload. | MUST |
| REQ-TEST-17 | Schema sanitization MUST be tested: a tool schema with `additionalProperties`, `$schema`, `default`, or `title` MUST have those keys removed in the outgoing payload. | MUST |
| REQ-TEST-18 | Message conversion MUST be tested: `UserMessage`, `AssistantMessage` (with and without content, with and without tool calls), and `ToolResultMessage` MUST produce correct Gemini API payloads. | MUST |
| REQ-TEST-19 | `systemInstruction` MUST appear at the top level, not inside `generationConfig`. | MUST |
| REQ-TEST-20 | A `functionResponse` part (tool result) MUST include correct `name` and `response.output`/`response.error` fields. | MUST |
| REQ-TEST-21 | Models must be detectable: `_is_gemini3_pro_model`, `_is_gemini3_flash_model`, `_is_gemma4_model` MUST be tested with known model strings. | MUST |
| REQ-TEST-22 | SSE parsing MUST be tested: valid `data:` lines, leading whitespace, missing `data:` prefix, and JSON decode errors MUST be handled gracefully. | MUST |
| REQ-TEST-23 | The `finishReason` normalization MUST be tested: `STOP`, `MAX_TOKENS`, `SAFETY`, and an empty/missing finish reason. | MUST |
| REQ-TEST-24 | Cancellation via `CancellationToken` during a retry wait MUST stop the retry and return immediately. | MUST |
| REQ-TEST-25 | The tests SHOULD use `httpx.MockTransport` or direct fake HTTP responses — no real HTTP calls. | SHOULD |
| REQ-TEST-26 | The tests MAY share helper utilities (`_collect`, payload assertions) with `test_tau_ai.py` via `conftest.py` or direct import. | MAY |

### 2. xhigh Thinking Level — REQ-XHIGH

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-XHIGH-1 | The provider MUST accept `"xhigh"` as a `reasoning_effort` value. | MUST |
| REQ-XHIGH-2 | For Gemini 3.x models (gemini-3-pro, gemini-3-flash), `"xhigh"` MUST map to `{"thinkingLevel": "HIGH"}` in the `thinkingConfig`. | MUST |
| REQ-XHIGH-3 | For Gemma 4 models, `"xhigh"` MUST map to `{"thinkingLevel": "HIGH"}`. | MUST |
| REQ-XHIGH-4 | For Gemini 2.5 models that support budgets, `"xhigh"` MUST fold to the "high" budget value (e.g., 32768 for 2.5-pro, 24576 for 2.5-flash). | MUST |
| REQ-XHIGH-5 | The current behavior of folding `xhigh` -> `high` (present in the code) MUST be preserved; the requirement is to verify and document it. | MUST |
| REQ-XHIGH-6 | If the API rejects `HIGH` thinking level for a model, the provider MUST fall back to `HIGH` (same level — documentation note: the fallback exists if the API rejects the model's specific level). | SHOULD |
| REQ-XHIGH-7 | A fallback SHOULD log a warning through the standard retry/error event mechanism. | SHOULD |
| REQ-XHIGH-8 | The `"xhigh"` folding-to-`"high"` logic SHOULD be centralized in a single helper to avoid duplication between `_google_budget` and `_google_level`. | SHOULD |

### 3. thoughtSignature Round-Trip — REQ-SIG

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-SIG-1 | `ToolCall` MUST carry an optional `thought_signature` field of type `str | None` with a default of `None`. | MUST |
| REQ-SIG-2 | The Google parser MUST extract `functionCall.thoughtSignature` from the Gemini SSE response and store it on the `ToolCall`. | MUST |
| REQ-SIG-3 | When building a subsequent `functionCall` part (inside `_message_to_google`), if the `ToolCall` has a non-None `thought_signature`, the provider MUST echo it as `thoughtSignature` in the API call. | MUST |
| REQ-SIG-4 | Tool calls without a `thought_signature` MUST NOT include a `thoughtSignature` field in the API payload. | MUST |
| REQ-SIG-5 | The `thought_signature` field MUST be `None` by default so that other providers (Anthropic, OpenAI, etc.) are unaffected. | MUST |
| REQ-SIG-6 | The `AssistantMessage.finalize()` event (in `ProviderResponseEndEvent`) MUST carry the `thought_signature` values on the embedded `ToolCall` objects. | MUST |
| REQ-SIG-7 | A multi-turn scenario MUST be tested: parse a response with `thoughtSignature`, echo it in the next request, verify the signature propagates through the full round-trip. | MUST |
| REQ-SIG-8 | The `thought_signature` field SHOULD be stored on `ToolCall` in `tau_agent/tools.py`, not in the Google provider. | SHOULD |

### 4. Schema Sanitization — REQ-SAN

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-SAN-1 | A function `_sanitize_google_schema()` MUST exist that recursively processes a JSON Schema dict. | MUST |
| REQ-SAN-2 | The function MUST remove the key `"additionalProperties"` at every level of the schema. | MUST |
| REQ-SAN-3 | The function MUST remove the key `"$schema"` at every level of the schema. | MUST |
| REQ-SAN-4 | The function MUST remove the key `"default"` at every level of the schema. | MUST |
| REQ-SAN-5 | The function MUST remove the key `"title"` at every level of the schema. | MUST |
| REQ-SAN-6 | The function MUST NOT mutate the original input dict — it SHOULD return a deep copy with the stripped schema. | MUST |
| REQ-SAN-7 | The sanitized schema MUST be used when building tool declarations in `_tool_to_google`. | MUST |
| REQ-SAN-8 | Nested schemas (`properties`, `items`, `allOf`, `anyOf`, `oneOf`, `not`, `additionalProperties` objects) MUST be recursively sanitized. | MUST |
| REQ-SAN-9 | Non-dict values that happen to be under a stripped key MUST be silently dropped (not validated or stored). | MUST |
| REQ-SAN-10 | A schema that has none of the banned keys MUST pass through unchanged (aside from the deep copy). | MUST |
| REQ-SAN-11 | The sanitization MUST be tested with schemas containing nested banned keys, schemas with no banned keys, and deeply nested schemas. | MUST |
| REQ-SAN-12 | The sanitization SHOULD handle edge cases: empty dict `{}`, `None` values for nested fields, array schemas with `items`. | SHOULD |

### 5. Thought Preservation — REQ-THOUGHT

| ID | Requirement | Priority |
|----|-------------|----------|
| REQ-THOUGHT-1 | `AssistantMessage` in `tau_agent/messages.py` MUST gain an optional `thinking_text` field of type `str` with a default of `""`. | MUST |
| REQ-THOUGHT-2 | When the Google parser accumulates thinking parts, the accumulated thinking text MUST be set on `AssistantMessage.thinking_text` in the final `ProviderResponseEndEvent`. | MUST |
| REQ-THOUGHT-3 | If no thinking parts were streamed, `thinking_text` MUST remain `""` (empty string, not `None`). | MUST |
| REQ-THOUGHT-4 | The `thinking_text` field is informational/preservation only — no agent loop behavior depends on it. | MUST |
| REQ-THOUGHT-5 | Other providers (Anthropic, OpenAI) MAY set `thinking_text` if they already preserve thinking content. | MAY |
| REQ-THOUGHT-6 | If adding `thinking_text` to `AssistantMessage` would require a model refactor that risks breaking other providers, the spec MUST document the limitation and accept a deferred implementation with a dev-note. | SHOULD |

## Scenarios

### SCEN-TEST-1: Thinking streaming
```
GIVEN a Google SSE response with a thinking part: {"text":"reasoning...","thought":true}
WHEN the provider streams the response
THEN a ProviderThinkingDeltaEvent with delta="reasoning..." MUST be emitted
AND the final AssistantMessage.thinking_text MUST contain "reasoning..."
```

### SCEN-TEST-2: Non-thinking text streaming
```
GIVEN a Google SSE response with a text part: {"text":"Hello"}
WHEN the provider streams the response
THEN a ProviderTextDeltaEvent with delta="Hello" MUST be emitted
AND the final AssistantMessage.content MUST contain "Hello"
```

### SCEN-TEST-3: Mixed thinking and text
```
GIVEN a Google SSE response with parts: [{"text":"think...","thought":true}, {"text":"output"}]
WHEN the provider streams the response
THEN the event sequence MUST be: thinking_delta("think..."), text_delta("output")
```

### SCEN-TEST-4: Tool call streaming
```
GIVEN a Google SSE response with a functionCall part
WHEN the provider streams the response
THEN a ProviderToolCallEvent MUST be emitted
AND the ToolCall.id MUST match the functionCall.id
AND the ToolCall.name MUST match the functionCall.name
AND the ToolCall.arguments MUST match the functionCall.args
```

### SCEN-TEST-5: Tool call with default ID
```
GIVEN a Google SSE response with a functionCall part that has no "id" field
WHEN the provider streams the response
THEN the ToolCall.id MUST be "tool-call-0"
```

### SCEN-TEST-6: Non-retryable HTTP error
```
GIVEN a Google SSE response with HTTP 400 (Bad Request)
WHEN the provider processes the response
THEN no retry MUST be attempted
AND a ProviderErrorEvent MUST be yielded
```

### SCEN-TEST-7: Retryable HTTP error succeeds on retry
```
GIVEN a Google SSE response with HTTP 429 on first attempt, then HTTP 200
AND max_retries >= 1
WHEN the provider streams the response
THEN a ProviderRetryEvent MUST be yielded
AND the stream MUST eventually succeed with ProviderResponseStartEvent + events
```

### SCEN-TEST-8: All retries exhausted
```
GIVEN a Google SSE response with HTTP 429 on all attempts
AND max_retries = 2
WHEN the provider streams the response
THEN exactly 2 ProviderRetryEvent events MUST be yielded
AND a final ProviderErrorEvent MUST be yielded
```

### SCEN-TEST-9: Network error without emitted content
```
GIVEN an httpx.HTTPError on the first attempt (no content emitted yet)
AND max_retries >= 1
WHEN the provider streams the response
THEN a ProviderRetryEvent MUST be yielded
```

### SCEN-TEST-10: Network error after content emitted
```
GIVEN content was already emitted from the stream (parser.emitted_content = True)
AND then an httpx.HTTPError occurs
WHEN the provider processes the error
THEN no retry MUST be attempted
AND a ProviderErrorEvent MUST be yielded
```

### SCEN-XHIGH-1: xhigh with Gemini 2.5 flash
```
GIVEN a model "gemini-2.5-flash" with reasoning_effort="xhigh"
WHEN the payload is built
THEN thinkingConfig MUST contain {"includeThoughts": True, "thinkingBudget": 24576}
```

### SCEN-XHIGH-2: xhigh with Gemini 3 pro
```
GIVEN a model "gemini-3-pro-v1" with reasoning_effort="xhigh"
WHEN the payload is built
THEN thinkingConfig MUST contain {"thinkingLevel": "HIGH"}
```

### SCEN-XHIGH-3: xhigh with Gemma 4
```
GIVEN a model "gemma-4-9b" with reasoning_effort="xhigh"
WHEN the payload is built
THEN thinkingConfig MUST contain {"thinkingLevel": "HIGH"}
```

### SCEN-SIG-1: thoughtSignature extracted from SSE
```
GIVEN a Google SSE response with: {"functionCall":{"name":"read","args":{},"thoughtSignature":"sig123"}}
WHEN the provider parses the part
THEN the ToolCall.thought_signature MUST be "sig123"
```

### SCEN-SIG-2: thoughtSignature echoed in next functionCall
```
GIVEN a ToolCall with thought_signature="sig123" inside an AssistantMessage
WHEN _message_to_google builds the payload
THEN the functionCall part MUST include "thoughtSignature": "sig123"
```

### SCEN-SIG-3: No thoughtSignature when absent
```
GIVEN a ToolCall with thought_signature=None inside an AssistantMessage
WHEN _message_to_google builds the payload
THEN the functionCall part MUST NOT contain a "thoughtSignature" key
```

### SCEN-SIG-4: Multi-turn round-trip
```
GIVEN a first response with thoughtSignature="abc"
AND the ToolCall with thought_signature="abc" is included in the AssistantMessage
AND the next request serializes that AssistantMessage
WHEN the second API payload is inspected
THEN it MUST contain "thoughtSignature":"abc" in the corresponding functionCall
```

### SCEN-SAN-1: additionalProperties stripped
```
GIVEN a tool schema containing "additionalProperties": false at the root and in properties
WHEN _sanitize_google_schema processes it
THEN the output MUST NOT contain "additionalProperties" at any level
```

### SCEN-SAN-2: $schema stripped
```
GIVEN a tool schema containing "$schema": "http://json-schema.org/draft-07/schema#"
WHEN _sanitize_google_schema processes it
THEN the output MUST NOT contain "$schema"
```

### SCEN-SAN-3: Multiple banned keys stripped
```
GIVEN a tool schema with additionalProperties, $schema, default, and title
WHEN sanitized
THEN all four keys MUST be absent from the output
```

### SCEN-SAN-4: Nested properties sanitized
```
GIVEN a schema with: {"type":"object","properties":{"nested":{"type":"object","additionalProperties":false}}}
WHEN sanitized
THEN the nested "additionalProperties" MUST be removed from the inner object
```

### SCEN-SAN-5: Clean schema unchanged
```
GIVEN a schema with no banned keys: {"type":"string","description":"A name"}
WHEN sanitized
THEN output MUST be structurally identical to input (deep copy, same content)
```

### SCEN-SAN-6: Original not mutated
```
GIVEN a schema dict containing additionalProperties
WHEN sanitized
THEN the original dict MUST still contain additionalProperties
```

### SCEN-THOUGHT-1: Thinking text in final AssistantMessage
```
GIVEN a stream with thinking parts producing "step1 step2"
WHEN ProviderResponseEndEvent is emitted
THEN event.message.thinking_text MUST be "step1 step2"
```

### SCEN-THOUGHT-2: No thinking leaves empty string
```
GIVEN a stream with no thinking parts
WHEN ProviderResponseEndEvent is emitted
THEN event.message.thinking_text MUST be ""
```

## Edge Cases

| ID | Edge Case | Expected Behaviour |
|----|-----------|-------------------|
| EC-1 | Empty SSE data line (`data:`) | Must be silently skipped |
| EC-2 | SSE line without `data:` prefix | Must be silently skipped |
| EC-3 | Malformed JSON in SSE data | Must be silently skipped (returns None from `_loads_object`) |
| EC-4 | SSE with missing `candidates` key | Must return empty event list |
| EC-5 | `candidates` is not a list | Must return empty event list |
| EC-6 | `candidates[0]` is not a Mapping | Must return empty event list |
| EC-7 | `content.parts` is not a list | Must return empty event list |
| EC-8 | `parts` contains non-Mapping entries | Non-Mapping entries must be silently skipped |
| EC-9 | `functionCall` with missing `name` | ToolCall.name must be `""` |
| EC-10 | `functionCall` with missing `args` | ToolCall.arguments must be `{}` |
| EC-11 | Multiple `finishReason` values across chunks | Last value wins (current behavior) |
| EC-12 | Schema sanitization with `None` value for `properties` | Must not crash; `None` must be preserved as-is |
| EC-13 | Schema sanitization with array type and `items` | Must recursively sanitize `items` |
| EC-14 | `_tool_to_google` called with tool that has empty `input_schema` | Must produce a parameters object with no banned keys |
| EC-15 | Cancellation during retry wait | Must stop waiting and return without error event |
| EC-16 | `reasoning_effort="none"` with model that doesn't match any branch | Must produce `{"thinkingBudget": 0}` |
| EC-17 | HTTP status 500 with non-JSON body | Error message must contain the raw body text (truncated) |
| EC-18 | SSE text part with `thought: true` but empty `text` | Must not emit a thinking delta event (empty string check) |
| EC-19 | SSE text part with empty `text` (not thought) | Must not emit a text delta event (empty string check) |

## Error Handling

| ID | Error | Behaviour |
|----|-------|-----------|
| EH-1 | HTTP 400 Bad Request | No retry; yield `ProviderErrorEvent` with descriptive message |
| EH-2 | HTTP 401 Unauthorized | No retry; yield `ProviderErrorEvent` |
| EH-3 | HTTP 403 Forbidden | No retry; yield `ProviderErrorEvent` |
| EH-4 | HTTP 404 Not Found | No retry; yield `ProviderErrorEvent` |
| EH-5 | HTTP 408 Request Timeout | Retry up to `max_retries` |
| EH-6 | HTTP 409 Conflict | Retry up to `max_retries` |
| EH-7 | HTTP 425 Too Early | Retry up to `max_retries` |
| EH-8 | HTTP 429 Too Many Requests | Retry up to `max_retries` |
| EH-9 | HTTP 500+ Server Error | Retry up to `max_retries` |
| EH-10 | Network timeout (httpx.TimeoutException) | Retry if no content emitted; yield `ProviderErrorEvent` otherwise |
| EH-11 | Connection reset (httpx.RemoteProtocolError) | Same as EH-10 |
| EH-12 | DNS resolution failure | Same as EH-10 |
| EH-13 | All retries exhausted | Final `ProviderErrorEvent` with number of attempts |
| EH-14 | Cancel during retry delay | Stop immediately, no error event |
| EH-15 | Unknown `reasoning_effort` value | Fall back to `HIGH` with `includeThoughts: True` |
| EH-16 | Google API rejects schema with unexpected keyword | Not handled by sanitization — this is a preemptive measure; if new keywords emerge, `_sanitize_google_schema` must be updated |

## Out of Scope

- **Multimodal support** (image, audio, video inputs)
- **New model families** (only current models: Gemini 2.5, Gemini 3.x, Gemma 4)
- **Response caching** (Google API caching headers)
- **Message model refactor** (the `thinking_text` field is the only addition to `AssistantMessage`)
- **Other providers** (OpenAI, Anthropic, Mistral thoughtSignature handling)
- **Agent loop changes** (no behavior changes in the harness, loop, or TUI)
- **Non-functionCall tool types** (Gemini `codeExecution`, `retrieval`, `googleSearch`)
- **System instruction hardening** (already at top level — just needs test coverage)
- **Streaming timeout** (timeout is connection-level via httpx, no per-chunk timeout)
- **Rate limiting beyond retry** (no client-side rate limiter)
- **Schema validation** (sanitization only — the provider does not validate schemas)
- **Conversation history trimming** (managed by the agent loop, not the provider)
