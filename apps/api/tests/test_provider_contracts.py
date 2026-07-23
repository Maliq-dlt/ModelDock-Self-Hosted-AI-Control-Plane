import httpx
import pytest

from app.models import ModelRecord, Provider
from app.providers.adapters import GeminiAdapter, OllamaAdapter, OpenAIAdapter
from app.schemas import ChatCompletionRequest


REQUEST = ChatCompletionRequest(model="alias", messages=[{"role": "user", "content": "hello"}])


@pytest.mark.asyncio
async def test_openai_adapter_contract(monkeypatch) -> None:
    adapter = OpenAIAdapter(Provider(name="openai", provider_type="openai"), ModelRecord(provider_id="provider", model_name="model"))

    async def fake_send(*args, **kwargs):
        assert "modeldock" not in kwargs["json"]
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 2, "completion_tokens": 1}})

    monkeypatch.setattr(adapter, "_send", fake_send)
    result = await adapter.chat(REQUEST)
    assert result.content == "ok"
    assert result.usage == {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_ollama_adapter_contract(monkeypatch) -> None:
    adapter = OllamaAdapter(Provider(name="ollama", provider_type="ollama"), ModelRecord(provider_id="provider", model_name="model"))

    async def fake_send(*args, **kwargs):
        return httpx.Response(200, json={"message": {"content": "local"}, "prompt_eval_count": 3, "eval_count": 2})

    monkeypatch.setattr(adapter, "_send", fake_send)
    result = await adapter.chat(REQUEST)
    assert result.content == "local"
    assert result.usage["total_tokens"] == 5
    assert result.finish_reason == "stop"


@pytest.mark.asyncio
async def test_gemini_adapter_contract(monkeypatch) -> None:
    adapter = GeminiAdapter(Provider(name="gemini", provider_type="gemini"), ModelRecord(provider_id="provider", model_name="model"))

    async def fake_send(*args, **kwargs):
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "gemini"}]}, "finishReason": "STOP"}], "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 2}})

    monkeypatch.setattr(adapter, "_send", fake_send)
    result = await adapter.chat(REQUEST)
    assert result.content == "gemini"
    assert result.usage == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    assert result.finish_reason == "stop"
