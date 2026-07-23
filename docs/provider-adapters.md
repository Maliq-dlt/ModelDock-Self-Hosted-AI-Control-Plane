# Provider Adapters

ModelDock keeps provider-specific HTTP details behind one internal adapter contract.

## Contract

`ProviderAdapter` exposes:

- `chat(request) -> ProviderResponse`;
- `stream_chat(request) -> AsyncIterator[ProviderStreamChunk]`;
- `health_check() -> bool`;
- `list_models() -> list[ProviderModel]`.

`ProviderResponse` always includes normalized text, usage, finish reason, raw provider payload, and optional tool calls. Gateway retry, quota, cost, trace, and protocol formatting do not depend on provider JSON.

## Built-ins

- `openai`: OpenAI Chat Completions.
- `openai_responses`: OpenAI Responses.
- `anthropic`: Anthropic Messages.
- `gemini`: Gemini generateContent.
- `groq`: OpenAI-compatible Groq endpoint.
- `ollama`: Ollama chat API.
- `openai_compatible`: custom Chat Completions endpoint.

Provider credentials stay encrypted. Account credentials override provider-level credentials only for the selected attempt.

## Account Pools

Provider accounts use priority order, then creation order. Account with `quota_remaining=0` is skipped while `quota_reset_at` is in the future. Expired reset clears the block before selection. No account means provider-level credentials remain valid fallback.

## Catalog Sync

```http
POST /api/providers/{provider_id}/models/sync
```

Sync upserts model name, display name, context window, and capabilities. Existing pricing and manual quality score stay intact unless provider returns pricing metadata.

## Custom Adapter

Register adapter at application startup:

```python
from app.providers.adapters import ProviderAdapter, ProviderResponse, register_adapter

class MyAdapter(ProviderAdapter):
    async def chat(self, request):
        ...

    async def health_check(self):
        ...

    async def list_models(self):
        ...

register_adapter("my_provider", MyAdapter)
```

Custom adapters must preserve full output and return normalized usage. Do not put credentials in source code.
