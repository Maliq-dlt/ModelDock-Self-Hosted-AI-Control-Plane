from fastapi.testclient import TestClient

from app.main import app
from app.providers.adapters import ProviderResponse, ProviderStreamChunk
import app.services.gateway as gateway


class CountingAdapter:
    calls = 0

    async def chat(self, request):
        type(self).calls += 1
        return ProviderResponse(content="advanced response", usage={"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}, finish_reason="stop", raw={})

    async def stream_chat(self, request):
        type(self).calls += 1
        yield ProviderStreamChunk(delta="stream ")
        yield ProviderStreamChunk(delta="works", finish_reason="stop", usage={"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10})


def test_rules_idempotency_stream_prompts_evaluations_and_admin_login(monkeypatch) -> None:
    CountingAdapter.calls = 0
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: CountingAdapter())
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "Advanced Project", "slug": "advanced-project"}).json()
        provider = client.post("/api/providers", headers=admin_headers, json={"name": "advanced-provider", "provider_type": "ollama", "base_url": "http://unused"}).json()
        model = client.post("/api/models", headers=admin_headers, json={"provider_id": provider["id"], "model_name": "advanced-model", "pricing": {"input_cost_per_million": 1, "output_cost_per_million": 1}, "capabilities": ["chat", "tools"], "tags": ["coding"]}).json()
        virtual = client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "coding-router", "strategy": "priority", "candidates": [{"model_id": model["id"]}]}).json()
        assert virtual["name"] == "coding-router"

        rule = client.post("/api/routing-rules", headers=admin_headers, json={"project_id": project["id"], "name": "coding", "priority": 10, "condition": {"task_type": "coding"}, "action": {"route_to": "coding-router", "require": {"capabilities": ["tools"], "tags": ["coding"]}}})
        assert rule.status_code == 201
        simulation = client.post("/api/routing-rules/simulate", headers=admin_headers, json={"project_id": project["id"], "model": "unknown-client-alias", "task_type": "coding", "estimated_prompt_tokens": 10})
        assert simulation.status_code == 200
        assert simulation.json()["decision"]["routing_rule"]["name"] == "coding"

        key_response = client.post("/api/api-keys", headers=admin_headers, json={"project_id": project["id"], "name": "advanced-client", "environment": "test", "allowed_models": ["unknown-client-alias"], "token_limit_monthly": 1000})
        raw_key = key_response.json()["raw_key"]
        gateway_headers = {"Authorization": f"Bearer {raw_key}", "Idempotency-Key": "same-request"}
        body = {"model": "unknown-client-alias", "task_type": "coding", "messages": [{"role": "user", "content": "write code"}]}
        first = client.post("/v1/chat/completions", headers=gateway_headers, json=body)
        second = client.post("/v1/chat/completions", headers=gateway_headers, json=body)
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        assert CountingAdapter.calls == 1

        stream_body = {**body, "stream": True}
        with client.stream("POST", "/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json=stream_body) as response:
            stream_text = "".join(response.iter_text())
        assert response.status_code == 200
        assert "stream " in stream_text
        assert "works" in stream_text
        assert "[DONE]" in stream_text

        prompt = client.post("/api/prompts", headers=admin_headers, json={"project_id": project["id"], "name": "support", "content": "Hello {{ name }}", "variables": ["name"]})
        assert prompt.status_code == 201
        rendered = client.post(f"/api/prompts/{prompt.json()['id']}/render", headers=admin_headers, json={"variables": {"name": "ModelDock"}})
        assert rendered.json()["content"] == "Hello ModelDock"

        evaluation = client.post("/api/evaluations/run", headers=admin_headers, json={"output_text": "advanced response", "checks": {"contains": "advanced", "min_length": 8}})
        assert evaluation.status_code == 201
        assert evaluation.json()["score"] == 1.0

        user = client.post("/api/auth/users", headers=admin_headers, json={"email": "owner@example.com", "password": "long-password-123", "role": "owner"})
        assert user.status_code == 201
        login = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "long-password-123"})
        assert login.status_code == 200
        projects = client.get("/api/projects", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
        assert projects.status_code == 200
