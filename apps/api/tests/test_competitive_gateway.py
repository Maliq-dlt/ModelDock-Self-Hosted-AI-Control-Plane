from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.security import encrypt_credentials
from app.main import app
from app.models import ModelRecord, Provider
from app.providers.adapters import (
    AnthropicAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapter,
    ProviderModel,
    ProviderResponse,
    ProviderStreamChunk,
    adapter_for,
    register_adapter,
)
from app.schemas import ChatCompletionRequest
import app.api.routes as routes
import app.services.gateway as gateway

REQUEST = ChatCompletionRequest(
    model="alias",
    messages=[{"role": "system", "content": "Be exact."}, {"role": "user", "content": "hello"}],
    temperature=0.2,
    max_completion_tokens=256,
)


@pytest.mark.asyncio
async def test_anthropic_adapter_contract(monkeypatch) -> None:
    provider = Provider(name="anthropic", provider_type="anthropic", encrypted_credentials=encrypt_credentials({"api_key": "secret"}))
    adapter = AnthropicAdapter(provider, ModelRecord(provider_id="provider", model_name="claude-test"))

    async def fake_send(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/messages")
        assert kwargs["headers"]["x-api-key"] == "secret"
        assert kwargs["json"]["temperature"] == 0.2
        assert kwargs["json"]["max_tokens"] == 256
        return httpx.Response(200, json={"content": [{"type": "text", "text": "anthropic ok"}], "stop_reason": "end_turn", "usage": {"input_tokens": 4, "output_tokens": 2}})

    monkeypatch.setattr(adapter, "_send", fake_send)
    result = await adapter.chat(REQUEST)
    assert result.content == "anthropic ok"
    assert result.usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}


@pytest.mark.asyncio
async def test_openai_responses_adapter_contract(monkeypatch) -> None:
    provider = Provider(name="responses", provider_type="openai_responses")
    adapter = OpenAIResponsesAdapter(provider, ModelRecord(provider_id="provider", model_name="gpt-test"))

    async def fake_send(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/responses")
        assert kwargs["json"]["instructions"] == "Be exact."
        assert kwargs["json"]["max_output_tokens"] == 256
        return httpx.Response(200, json={"output_text": "responses ok", "output": [], "usage": {"input_tokens": 3, "output_tokens": 2}})

    monkeypatch.setattr(adapter, "_send", fake_send)
    result = await adapter.chat(REQUEST)
    assert result.content == "responses ok"
    assert result.usage["total_tokens"] == 5


@pytest.mark.asyncio
async def test_adapter_registry_supports_external_adapter() -> None:
    class CustomAdapter(ProviderAdapter):
        async def chat(self, request):
            return ProviderResponse(content="custom", usage={}, finish_reason="stop", raw={})

        async def health_check(self):
            return True

        async def list_models(self):
            return []

    register_adapter("test_sdk_adapter", CustomAdapter)
    adapter = adapter_for(Provider(name="custom", provider_type="test_sdk_adapter"), ModelRecord(provider_id="provider", model_name="model"))
    assert isinstance(adapter, CustomAdapter)


class CapturePoolAdapter:
    selected_accounts: list[str | None] = []

    def __init__(self, account) -> None:
        self.account = account

    async def chat(self, request):
        type(self).selected_accounts.append(self.account.name if self.account else None)
        return ProviderResponse(content="full capability output", usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}, finish_reason="stop", raw={})

    async def stream_chat(self, request):
        type(self).selected_accounts.append(self.account.name if self.account else None)
        yield ProviderStreamChunk(delta="full ")
        yield ProviderStreamChunk(delta="stream", finish_reason="stop", usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})


def test_protocol_endpoints_use_quota_reset_aware_account_pool(monkeypatch) -> None:
    CapturePoolAdapter.selected_accounts = []
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model, account=None: CapturePoolAdapter(account))
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    now = datetime.now(timezone.utc)
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "Protocol Project", "slug": "protocol-project"}).json()
        provider = client.post("/api/providers", headers=admin_headers, json={"name": "protocol-provider", "provider_type": "ollama", "base_url": "http://unused"}).json()
        model = client.post("/api/models", headers=admin_headers, json={"provider_id": provider["id"], "model_name": "protocol-model"}).json()
        client.post("/api/providers/{}/accounts".format(provider["id"]), headers=admin_headers, json={"name": "blocked", "credentials": {"api_key": "blocked"}, "priority": 0, "quota_remaining": 0, "quota_reset_at": (now + timedelta(hours=1)).isoformat()})
        reset_ready = client.post("/api/providers/{}/accounts".format(provider["id"]), headers=admin_headers, json={"name": "reset-ready", "credentials": {"api_key": "ready"}, "priority": 1, "quota_remaining": 0, "quota_reset_at": (now - timedelta(seconds=1)).isoformat()}).json()
        key = client.post("/api/api-keys", headers=admin_headers, json={"project_id": project["id"], "name": "protocol-client", "environment": "test"}).json()["raw_key"]

        responses_result = client.post("/v1/responses", headers={"Authorization": f"Bearer {key}", "Idempotency-Key": "cross-protocol"}, json={"model": model["model_name"], "input": "Preserve output."})
        assert responses_result.status_code == 200
        assert responses_result.json()["object"] == "response"
        assert responses_result.json()["output_text"] == "full capability output"
        trace = client.get(f"/api/traces/{responses_result.headers['X-ModelDock-Trace-ID']}", headers=admin_headers).json()
        assert trace["metadata"]["selected"]["account"] == "reset-ready"
        assert trace["attempts"][0]["provider_account_id"] == reset_ready["id"]

        messages_result = client.post("/v1/messages", headers={"x-api-key": key}, json={"model": model["model_name"], "max_tokens": 128, "messages": [{"role": "user", "content": "Keep capability."}]})
        assert messages_result.status_code == 200
        assert messages_result.json()["type"] == "message"
        assert messages_result.json()["content"][0]["text"] == "full capability output"

        conflict = client.post("/v1/messages", headers={"x-api-key": key, "Idempotency-Key": "cross-protocol"}, json={"model": model["model_name"], "max_tokens": 128, "messages": [{"role": "user", "content": "Conflict."}]})
        assert conflict.status_code == 409
        assert conflict.json()["type"] == "error"
        assert conflict.headers["X-ModelDock-Trace-ID"] == responses_result.headers["X-ModelDock-Trace-ID"]

        with client.stream("POST", "/v1/responses", headers={"Authorization": f"Bearer {key}"}, json={"model": model["model_name"], "input": "Stream.", "stream": True}) as streamed:
            stream_text = "".join(streamed.iter_text())
        assert streamed.status_code == 200
        assert "response.created" in stream_text
        assert "response.output_text.delta" in stream_text
        assert "response.completed" in stream_text
        assert CapturePoolAdapter.selected_accounts == ["reset-ready", "reset-ready", "reset-ready"]


def test_provider_model_catalog_sync(monkeypatch) -> None:
    class CatalogAdapter:
        async def list_models(self):
            return [ProviderModel(model_name="catalog-model", display_name="Catalog Model", context_window=32000, capabilities=["chat", "tools"])]

    monkeypatch.setattr(routes, "adapter_for", lambda provider, model, account=None: CatalogAdapter())
    headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        provider = client.post("/api/providers", headers=headers, json={"name": "catalog-provider", "provider_type": "openai", "credentials": {"api_key": "secret"}}).json()
        synced = client.post(f"/api/providers/{provider['id']}/models/sync", headers=headers)
        assert synced.status_code == 200
        assert synced.json()["synced"] == 1
        assert synced.json()["models"][0]["model_name"] == "catalog-model"
        assert synced.json()["models"][0]["context_window"] == 32000
