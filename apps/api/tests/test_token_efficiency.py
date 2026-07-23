from fastapi.testclient import TestClient

from app.main import app
from app.providers.adapters import ProviderResponse
from app.schemas import ChatCompletionRequest
import app.services.gateway as gateway
from app.services.token_efficiency import CAVEMAN_INSTRUCTION, PONYTAIL_INSTRUCTION, optimize_request


def test_safe_mode_compacts_tool_json_without_touching_user_content() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "router",
            "max_tokens": 2048,
            "messages": [
                {"role": "user", "content": "Preserve this exact request."},
                {"role": "tool", "tool_call_id": "call_1", "content": '{\n  "ok": true,\n  "items": [1, 2]\n}'},
            ],
            "modeldock": {"token_mode": "safe"},
        }
    )
    optimized, stats = optimize_request(request)

    assert optimized.messages[0].content == "Preserve this exact request."
    assert optimized.messages[1].content == '{"ok":true,"items":[1,2]}'
    assert optimized.messages[1].tool_call_id == "call_1"
    assert optimized.max_tokens == 2048
    assert stats["lossless_input"] is True
    assert stats["compacted_tool_messages"] == 1
    assert stats["input_tokens_saved"] > 0


def test_stacked_mode_adds_output_guidance_without_output_truncation() -> None:
    request = ChatCompletionRequest.model_validate(
        {
            "model": "router",
            "max_completion_tokens": 4096,
            "messages": [{"role": "system", "content": "Existing policy."}, {"role": "user", "content": "Implement feature."}],
            "modeldock": {"token_mode": "stacked"},
        }
    )
    optimized, stats = optimize_request(request)

    system = str(optimized.messages[0].content)
    assert CAVEMAN_INSTRUCTION in system
    assert PONYTAIL_INSTRUCTION in system
    assert optimized.max_completion_tokens == 4096
    assert stats["output_transform"] == "none"


class CaptureAdapter:
    request = None

    async def chat(self, request):
        type(self).request = request
        return ProviderResponse(
            content="Full output preserved.\n```python\nprint('capability')\n```",
            usage={"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20},
            finish_reason="stop",
            raw={},
        )


def test_tokenpress_integrates_with_gateway_without_output_postprocessing(monkeypatch) -> None:
    CaptureAdapter.request = None
    monkeypatch.setattr(gateway, "adapter_for", lambda provider, model: CaptureAdapter())
    admin_headers = {"X-ModelDock-Admin-Key": "test-admin-key"}
    with TestClient(app) as client:
        project = client.post("/api/projects", headers=admin_headers, json={"name": "TokenPress Project", "slug": "tokenpress-project"}).json()
        provider = client.post("/api/providers", headers=admin_headers, json={"name": "tokenpress-provider", "provider_type": "ollama", "base_url": "http://unused"}).json()
        model = client.post("/api/models", headers=admin_headers, json={"provider_id": provider["id"], "model_name": "tokenpress-model"}).json()
        raw_key = client.post("/api/api-keys", headers=admin_headers, json={"project_id": project["id"], "name": "tokenpress-client", "environment": "test"}).json()["raw_key"]

        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {raw_key}"},
            json={
                "model": model["model_name"],
                "messages": [
                    {"role": "user", "content": "Keep full output capability."},
                    {"role": "tool", "tool_call_id": "call_1", "content": '{\n  "ok": true,\n  "items": [1, 2]\n}'},
                ],
                "modeldock": {"token_mode": "safe"},
            },
        )

        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "Full output preserved.\n```python\nprint('capability')\n```"
        assert CaptureAdapter.request.messages[1].content == '{"ok":true,"items":[1,2]}'
        trace = client.get(f"/api/traces/{response.headers['X-ModelDock-Trace-ID']}", headers=admin_headers).json()
        assert trace["metadata"]["token_efficiency"]["mode"] == "safe"
        assert trace["metadata"]["token_efficiency"]["output_transform"] == "none"
