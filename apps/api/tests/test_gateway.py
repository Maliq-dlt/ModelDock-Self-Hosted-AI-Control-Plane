from contextlib import asynccontextmanager

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.providers.adapters import ProviderError, ProviderResponse, ProviderStreamChunk
import app.api.routes as routes
import app.services.gateway as gateway


class FakeAdapter:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def chat(self, request):
        if self.model_name == "primary-model":
            raise ProviderError(503, "provider_unavailable", "primary failed", retryable=False)
        return ProviderResponse(content="fallback worked", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}, finish_reason="stop", raw={})


def test_openai_gateway_fallback_trace_usage_and_budget(monkeypatch) -> None:
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: FakeAdapter(model.model_name))
    headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project_response = client.post("/api/projects", headers=headers, json={"name": "Test Project", "slug": "test-project"})
        assert project_response.status_code == 201
        project = project_response.json()

        model_ids = []
        for name, model_name in (("primary", "primary-model"), ("fallback", "fallback-model")):
            provider_response = client.post("/api/providers", headers=headers, json={"name": name, "provider_type": "ollama", "base_url": "http://unused"})
            assert provider_response.status_code == 201
            provider_id = provider_response.json()["id"]
            model_response = client.post("/api/models", headers=headers, json={"provider_id": provider_id, "model_name": model_name, "pricing": {"input_cost_per_million": 1, "output_cost_per_million": 2}})
            assert model_response.status_code == 201
            model_ids.append(model_response.json()["id"])

        virtual_response = client.post("/api/virtual-models", headers=headers, json={"project_id": project["id"], "name": "smart-router", "strategy": "priority", "candidates": [{"model_id": model_ids[0]}, {"model_id": model_ids[1]}]})
        assert virtual_response.status_code == 201

        key_response = client.post("/api/api-keys", headers=headers, json={"project_id": project["id"], "name": "test-client", "environment": "test"})
        assert key_response.status_code == 201
        raw_key = key_response.json()["raw_key"]

        completion = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "smart-router", "messages": [{"role": "user", "content": "hello"}]})
        assert completion.status_code == 200
        assert completion.json()["choices"][0]["message"]["content"] == "fallback worked"
        trace_id = completion.headers["X-ModelDock-Trace-ID"]

        trace = client.get(f"/api/traces/{trace_id}", headers=headers)
        assert trace.status_code == 200
        assert [attempt["status"] for attempt in trace.json()["attempts"]] == ["error", "success"]
        assert trace.json()["metadata"]["selected"]["provider"] == "fallback"

        usage = client.get("/api/usage/summary", headers=headers)
        assert usage.status_code == 200
        assert usage.json()["requests"] == 1
        assert usage.json()["total_tokens"] == 15

        budget = client.post("/api/budgets", headers=headers, json={"scope_id": project["id"], "limit_amount": 0.00001, "action_at_limit": "block"})
        assert budget.status_code == 201
        blocked = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "smart-router", "messages": [{"role": "user", "content": "blocked"}]})
        assert blocked.status_code == 402
        assert blocked.json()["error"]["type"] == "budget_exceeded"
        blocked_trace = client.get(f"/api/traces/{blocked.headers['X-ModelDock-Trace-ID']}", headers=headers)
        assert blocked_trace.status_code == 200
        assert blocked_trace.json()["status"] == "blocked"


class PartialStreamAdapter:
    calls: list[str] = []

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    async def stream_chat(self, request):
        type(self).calls.append(self.model_name)
        if self.model_name == "partial-primary-model":
            yield ProviderStreamChunk(delta="partial output")
            raise ProviderError(503, "provider_unavailable", "stream failed", retryable=True)
        yield ProviderStreamChunk(delta="fallback output", finish_reason="stop")


def test_stream_does_not_fallback_after_partial_output(monkeypatch) -> None:
    PartialStreamAdapter.calls = []
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: PartialStreamAdapter(model.model_name))
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "Stream Project", "slug": "stream-project"}).json()
        model_ids = []
        for provider_name, model_name in (("partial-primary", "partial-primary-model"), ("stream-fallback", "stream-fallback-model")):
            provider = client.post("/api/providers", headers=admin_headers, json={"name": provider_name, "provider_type": "ollama", "base_url": "http://unused"}).json()
            model = client.post("/api/models", headers=admin_headers, json={"provider_id": provider["id"], "model_name": model_name}).json()
            model_ids.append(model["id"])
        client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "stream-router", "strategy": "priority", "candidates": [{"model_id": model_ids[0]}, {"model_id": model_ids[1]}]})
        raw_key = client.post("/api/api-keys", headers=admin_headers, json={"project_id": project["id"], "name": "stream-client", "environment": "test"}).json()["raw_key"]

        with client.stream("POST", "/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "stream-router", "stream": True, "messages": [{"role": "user", "content": "hello"}]}) as response:
            body = "".join(response.iter_text())

        assert response.status_code == 200
        assert "partial output" in body
        assert "fallback output" not in body
        assert "provider_unavailable" in body
        assert PartialStreamAdapter.calls == ["partial-primary-model"]


def test_stream_concurrency_limit_returns_429_before_sse(monkeypatch) -> None:
    @asynccontextmanager
    async def denied_slot(subject, limit):
        raise HTTPException(status_code=429, detail="Concurrent request limit exceeded")
        yield

    monkeypatch.setattr(routes, "request_slot", denied_slot)
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "Limited Stream Project", "slug": "limited-stream-project"}).json()
        raw_key = client.post("/api/api-keys", headers=admin_headers, json={"project_id": project["id"], "name": "limited-stream-client", "environment": "test"}).json()["raw_key"]
        response = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "unused", "stream": True, "messages": [{"role": "user", "content": "hello"}]})

        assert response.status_code == 429
        assert response.json()["error"]["type"] == "concurrency_limit"
