import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.core.db import session_factory
from app.main import app
from app.models import Provider
from app.providers.adapters import ProviderResponse
import app.services.evaluations as evaluations


def test_upgrade_routing_resilience_rbac_and_evaluation(monkeypatch) -> None:
    class JudgeAdapter:
        async def chat(self, request):
            return ProviderResponse(content='{"score": 0.8, "reason": "meets rubric"}', usage={}, finish_reason="stop", raw={})

    monkeypatch.setattr(evaluations, "adapter_for", lambda provider, model: JudgeAdapter())
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "Upgrade Project", "slug": "upgrade-project"}).json()
        provider_a = client.post("/api/providers", headers=admin_headers, json={"name": "upgrade-a", "provider_type": "ollama", "base_url": "http://a", "concurrency_limit": 2}).json()
        provider_b = client.post("/api/providers", headers=admin_headers, json={"name": "upgrade-b", "provider_type": "ollama", "base_url": "http://b", "concurrency_limit": 3}).json()
        model_a = client.post("/api/models", headers=admin_headers, json={"provider_id": provider_a["id"], "model_name": "upgrade-a-model", "quality_score": 0.7}).json()
        model_b = client.post("/api/models", headers=admin_headers, json={"provider_id": provider_b["id"], "model_name": "upgrade-b-model", "quality_score": 0.9}).json()

        async def set_provider_state() -> None:
            async with session_factory() as session:
                first = await session.get(Provider, provider_a["id"])
                second = await session.get(Provider, provider_b["id"])
                first.last_health_latency_ms = 250
                second.last_health_latency_ms = 50
                first.reliability_score = 0.5
                second.reliability_score = 0.95
                await session.commit()

        asyncio.run(set_provider_state())
        fastest = client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "fastest", "strategy": "fastest", "candidates": [{"model_id": model_a["id"]}, {"model_id": model_b["id"]}]}).json()
        score = client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "score", "strategy": "weighted_score", "candidates": [{"model_id": model_a["id"]}, {"model_id": model_b["id"]}]}).json()
        weighted = client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "weighted", "strategy": "weighted_random", "candidates": [{"model_id": model_a["id"], "weight": 0}, {"model_id": model_b["id"], "weight": 1}]}).json()
        invalid_weight = client.post("/api/virtual-models", headers=admin_headers, json={"project_id": project["id"], "name": "invalid-weight", "strategy": "weighted_random", "candidates": [{"model_id": model_a["id"], "weight": "invalid"}]})
        assert invalid_weight.status_code == 422
        assert fastest["strategy"] == "fastest"
        assert score["strategy"] == "weighted_score"
        assert weighted["strategy"] == "weighted_random"

        fastest_result = client.post("/api/routing-rules/simulate", headers=admin_headers, json={"project_id": project["id"], "model": "fastest", "estimated_prompt_tokens": 10}).json()
        assert fastest_result["candidates"][0]["provider"] == "upgrade-b"
        score_result = client.post("/api/routing-rules/simulate", headers=admin_headers, json={"project_id": project["id"], "model": "score", "estimated_prompt_tokens": 10}).json()
        assert score_result["decision"]["reason"] == "weighted score strategy"
        assert score_result["candidates"][0]["provider"] == "upgrade-b"
        weighted_result = client.post("/api/routing-rules/simulate", headers=admin_headers, json={"project_id": project["id"], "model": "weighted", "estimated_prompt_tokens": 10}).json()
        assert weighted_result["candidates"][0]["provider"] == "upgrade-b"

        async def open_circuit() -> None:
            async with session_factory() as session:
                provider = await session.get(Provider, provider_b["id"])
                provider.circuit_open_until = datetime.now(timezone.utc) + timedelta(minutes=1)
                await session.commit()

        asyncio.run(open_circuit())
        circuit_result = client.post("/api/routing-rules/simulate", headers=admin_headers, json={"project_id": project["id"], "model": "fastest", "estimated_prompt_tokens": 10}).json()
        assert circuit_result["candidates"][0]["provider"] == "upgrade-a"
        assert any("circuit breaker open" in item["reason"] for item in circuit_result["decision"]["rejected_candidates"])

        queued = client.post("/api/evaluations/run", headers=admin_headers, json={"asynchronous": True, "output_text": "hello upgrade", "checks": {"contains": "upgrade"}})
        assert queued.status_code == 202
        processed = client.post("/api/evaluations/process-next", headers=admin_headers)
        assert processed.status_code == 200
        assert processed.json()["evaluation"]["status"] == "completed"

        judged = client.post("/api/evaluations/run", headers=admin_headers, json={"evaluation_type": "llm_judge", "output_text": "good answer", "judge_model_id": model_a["id"], "rubric": "Be correct"})
        assert judged.status_code == 201
        assert judged.json()["score"] == 0.8

        admin_user = client.post("/api/auth/users", headers=admin_headers, json={"email": "upgrade-admin@example.com", "password": "long-password-123", "role": "admin"})
        assert admin_user.status_code == 201
        admin_login = client.post("/api/auth/login", json={"email": "upgrade-admin@example.com", "password": "long-password-123"}).json()
        admin_session_headers = {"Authorization": f"Bearer {admin_login['access_token']}"}
        denied_owner = client.post("/api/auth/users", headers=admin_session_headers, json={"email": "denied-owner@example.com", "password": "long-password-123", "role": "owner"})
        assert denied_owner.status_code == 403

        viewer = client.post("/api/auth/users", headers=admin_headers, json={"email": "upgrade-viewer@example.com", "password": "long-password-123", "role": "viewer"})
        assert viewer.status_code == 201
        login = client.post("/api/auth/login", json={"email": "upgrade-viewer@example.com", "password": "long-password-123"}).json()
        viewer_headers = {"Authorization": f"Bearer {login['access_token']}"}
        assert client.get("/api/projects", headers=viewer_headers).status_code == 200
        assert client.post("/api/projects", headers=viewer_headers, json={"name": "Denied", "slug": "denied"}).status_code == 403
        assert client.get("/api/auth/me", headers=viewer_headers).status_code == 200
        assert client.post("/api/auth/logout-all", headers=viewer_headers).status_code == 200
        assert client.get("/api/projects", headers=viewer_headers).status_code == 401