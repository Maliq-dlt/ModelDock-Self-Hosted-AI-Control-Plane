from hashlib import sha256

from fastapi.testclient import TestClient

from app.main import app
from app.providers.adapters import ProviderResponse
import app.services.gateway as gateway

ADMIN_HEADERS = {"X-ModelDock-Admin-Key": "test-admin-key"}

class CaptureAdapter:
    requests = []

    async def chat(self, request):
        type(self).requests.append(request)
        return ProviderResponse(
            content="stage three response",
            usage={"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            finish_reason="stop",
            raw={},
        )

def _direct_route(client: TestClient, slug: str) -> tuple[dict, str, str]:
    project = client.post("/api/projects", headers=ADMIN_HEADERS, json={"name": slug, "slug": slug.lower().replace(" ", "-")}).json()
    provider = client.post("/api/providers", headers=ADMIN_HEADERS, json={"name": f"{slug}-provider", "provider_type": "ollama", "base_url": "http://unused"}).json()
    model = client.post("/api/models", headers=ADMIN_HEADERS, json={"provider_id": provider["id"], "model_name": f"{slug}-model"}).json()
    raw_key = client.post("/api/api-keys", headers=ADMIN_HEADERS, json={"project_id": project["id"], "name": f"{slug}-key", "environment": "test"}).json()["raw_key"]
    return project, raw_key, model["model_name"]

def _canary_key(variant: bool) -> str:
    for index in range(10_000):
        value = f"stage3-routing-{index}"
        bucket = int(sha256(value.encode()).hexdigest()[:8], 16) % 10_000 / 100
        if (bucket < 50) == variant:
            return value
    raise AssertionError("could not find deterministic canary key")

def test_token_policy_inherits_and_request_override_wins(monkeypatch) -> None:
    CaptureAdapter.requests = []
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: CaptureAdapter())
    with TestClient(app) as client:
        project, raw_key, model_name = _direct_route(client, "Stage3 Policy")
        policy = client.patch(f"/api/projects/{project['id']}/token-policy", headers=ADMIN_HEADERS, json={"safe": False, "caveman": True, "ponytail": False})
        assert policy.status_code == 200
        inherited = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": model_name, "messages": [{"role": "user", "content": "hello"}]})
        assert inherited.status_code == 200
        assert CaptureAdapter.requests[-1].modeldock.token_mode == "caveman"
        assert any("Answer concise" in str(message.content) for message in CaptureAdapter.requests[-1].messages if message.role == "system")

        overridden = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": model_name, "modeldock": {"token_mode": "off"}, "messages": [{"role": "user", "content": "hello"}]})
        assert overridden.status_code == 200
        assert CaptureAdapter.requests[-1].modeldock.token_mode == "off"
        assert all(message.role != "system" for message in CaptureAdapter.requests[-1].messages)

        client.patch(f"/api/projects/{project['id']}/token-policy", headers=ADMIN_HEADERS, json={"safe": True, "caveman": False, "ponytail": False})
        compacted = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": model_name, "messages": [{"role": "tool", "content": "{\n  \"payload\": [1, 2, 3, 4, 5],\n  \"message\": \"hello world\"\n}"}]})
        assert compacted.status_code == 200
        summary = client.get("/api/usage/summary", headers=ADMIN_HEADERS).json()
        assert summary["input_tokens"] >= 5
        assert summary["output_tokens"] >= 3
        assert summary["input_tokens_saved"] > 0
        points = client.get("/api/usage/timeseries?days=3", headers=ADMIN_HEADERS).json()
        assert len(points) == 3
        assert all({"input_tokens", "output_tokens", "tokens"}.issubset(point) for point in points)

def test_canary_is_deterministic_and_replay_does_not_call_provider(monkeypatch) -> None:
    CaptureAdapter.requests = []
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: CaptureAdapter())
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=ADMIN_HEADERS, json={"name": "Stage3 Canary", "slug": "stage3-canary"}).json()
        model_ids = []
        for suffix in ("control", "variant"):
            provider = client.post("/api/providers", headers=ADMIN_HEADERS, json={"name": f"canary-{suffix}-provider", "provider_type": "ollama", "base_url": "http://unused"}).json()
            model = client.post("/api/models", headers=ADMIN_HEADERS, json={"provider_id": provider["id"], "model_name": f"canary-{suffix}-model"}).json()
            model_ids.append(model["id"])
        virtual = client.post("/api/virtual-models", headers=ADMIN_HEADERS, json={"project_id": project["id"], "name": "canary-router", "strategy": "canary", "strategy_config": {"canary_percent": 50}, "candidates": [{"model_id": model_ids[0]}, {"model_id": model_ids[1]}]}).json()
        variant_key = _canary_key(True)
        first = client.post("/api/routing-rules/simulate", headers=ADMIN_HEADERS, json={"project_id": project["id"], "model": virtual["name"], "metadata": {"routing_key": variant_key}}).json()
        second = client.post("/api/routing-rules/simulate", headers=ADMIN_HEADERS, json={"project_id": project["id"], "model": virtual["name"], "metadata": {"routing_key": variant_key}}).json()
        assert first["decision"]["canary_lane"] == "variant"
        assert first["decision"]["canary_bucket"] == second["decision"]["canary_bucket"]
        assert first["candidates"] == second["candidates"]

        raw_key = client.post("/api/api-keys", headers=ADMIN_HEADERS, json={"project_id": project["id"], "name": "canary-key", "environment": "test"}).json()["raw_key"]
        completion = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {raw_key}"}, json={"model": "canary-router", "metadata": {"routing_key": variant_key}, "messages": [{"role": "user", "content": "hello"}]})
        assert completion.status_code == 200
        trace_id = completion.headers["X-ModelDock-Trace-ID"]
        CaptureAdapter.requests = []
        replay = client.get(f"/api/traces/{trace_id}/replay", headers=ADMIN_HEADERS)
        assert replay.status_code == 200
        assert replay.json()["status"] == "ready"
        assert replay.json()["changed"] is False
        assert CaptureAdapter.requests == []