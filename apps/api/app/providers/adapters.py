import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from app.core.security import decrypt_credentials
from app.models import ModelRecord, Provider
from app.schemas import ChatCompletionRequest

RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

class ProviderError(Exception):
    def __init__(self, status_code: int, error_type: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.message = message
        self.retryable = retryable
        self.trace_id: str | None = None

@dataclass
class ProviderResponse:
    content: str
    usage: dict[str, int]
    finish_reason: str
    raw: dict[str, Any]
    tool_calls: list[dict[str, Any]] | None = None

@dataclass
class ProviderStreamChunk:
    delta: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] | None = None

def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict))
    return str(content or "")

def _usage(value: dict[str, Any] | None) -> dict[str, int]:
    value = value or {}
    prompt = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
    completion = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}

async def _ensure_stream_response(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    body = await response.aread()
    try:
        payload = json.loads(body.decode() or "{}")
        detail = payload.get("error", payload)
        message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
        error_type = detail.get("type", "provider_error") if isinstance(detail, dict) else "provider_error"
    except (ValueError, UnicodeDecodeError):
        message = body.decode(errors="replace")[:500] or response.reason_phrase
        error_type = "provider_error"
    raise ProviderError(response.status_code, error_type, message, response.status_code in RETRYABLE_STATUS_CODES or response.status_code >= 500)

class ProviderAdapter:
    def __init__(self, provider: Provider, model: ModelRecord) -> None:
        self.provider = provider
        self.model = model
        self.credentials = decrypt_credentials(provider.encrypted_credentials)

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        raise NotImplementedError

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        response = await self.chat(request)
        yield ProviderStreamChunk(delta=response.content, finish_reason=response.finish_reason, usage=response.usage)

    async def health_check(self) -> bool:
        raise NotImplementedError

    async def _send(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
                response = await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc
        if response.status_code >= 400:
            try:
                payload = response.json()
                detail = payload.get("error", payload)
                message = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
                error_type = detail.get("type", "provider_error") if isinstance(detail, dict) else "provider_error"
            except ValueError:
                message = response.text[:500] or response.reason_phrase
                error_type = "provider_error"
            raise ProviderError(response.status_code, error_type, message, response.status_code in RETRYABLE_STATUS_CODES or response.status_code >= 500)
        return response

    def _openai_url(self) -> str:
        return f"{self._base_url()}/chat/completions"

    def _auth_headers(self) -> dict[str, str]:
        headers = {str(key): str(value) for key, value in (self.credentials.get("headers") or {}).items()}
        api_key = self.credentials.get("api_key")
        if api_key:
            headers.setdefault("Authorization", f"Bearer {api_key}")
        return headers

    def _base_url(self) -> str:
        return (self.provider.base_url or "https://api.openai.com/v1").rstrip("/")

class OpenAIAdapter(ProviderAdapter):
    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        payload = request.model_dump(exclude_none=True, exclude={"task_type", "data_classification", "metadata"})
        payload["model"] = self.model.model_name
        payload["stream"] = False
        response = await self._send("POST", self._openai_url(), json=payload, headers=self._auth_headers())
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return ProviderResponse(
            content=_content_to_text(message.get("content")),
            usage=_usage(body.get("usage")),
            finish_reason=choice.get("finish_reason") or "stop",
            raw=body,
            tool_calls=message.get("tool_calls"),
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        payload = request.model_dump(exclude_none=True, exclude={"task_type", "data_classification", "metadata"})
        payload["model"] = self.model.model_name
        payload["stream"] = True
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", self._openai_url(), json=payload, headers=self._auth_headers()) as response:
                    await _ensure_stream_response(response)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        value = line.removeprefix("data:").strip()
                        if value == "[DONE]":
                            break
                        try:
                            body = json.loads(value)
                        except json.JSONDecodeError:
                            continue
                        choice = (body.get("choices") or [{}])[0]
                        delta = (choice.get("delta") or {}).get("content") or ""
                        usage = _usage(body.get("usage")) if body.get("usage") else None
                        yield ProviderStreamChunk(delta=delta, finish_reason=choice.get("finish_reason"), usage=usage)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc

    async def health_check(self) -> bool:
        response = await self._send("GET", f"{self._base_url()}/models", headers=self._auth_headers())
        return response.status_code == 200

class GroqAdapter(OpenAIAdapter):
    def _base_url(self) -> str:
        return (self.provider.base_url or "https://api.groq.com/openai/v1").rstrip("/")

class OpenAICompatibleAdapter(OpenAIAdapter):
    pass

class OllamaAdapter(ProviderAdapter):
    def _base_url(self) -> str:
        return (self.provider.base_url or "http://host.docker.internal:11434").rstrip("/")

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        payload = {"model": self.model.model_name, "messages": [message.model_dump(exclude_none=True) for message in request.messages], "stream": False}
        options = {key: value for key, value in {"temperature": request.temperature, "top_p": request.top_p, "num_predict": request.max_tokens or request.max_completion_tokens}.items() if value is not None}
        if options:
            payload["options"] = options
        response = await self._send("POST", f"{self._base_url()}/api/chat", json=payload)
        body = response.json()
        return ProviderResponse(
            content=_content_to_text((body.get("message") or {}).get("content")),
            usage=_usage({"prompt_tokens": body.get("prompt_eval_count", 0), "completion_tokens": body.get("eval_count", 0)}),
            finish_reason="stop",
            raw=body,
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        payload = {"model": self.model.model_name, "messages": [message.model_dump(exclude_none=True) for message in request.messages], "stream": True}
        options = {key: value for key, value in {"temperature": request.temperature, "top_p": request.top_p, "num_predict": request.max_tokens or request.max_completion_tokens}.items() if value is not None}
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", f"{self._base_url()}/api/chat", json=payload) as response:
                    await _ensure_stream_response(response)
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            body = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        message = body.get("message") or {}
                        usage = None
                        if body.get("done"):
                            usage = _usage({"prompt_tokens": body.get("prompt_eval_count", 0), "completion_tokens": body.get("eval_count", 0)})
                        yield ProviderStreamChunk(delta=_content_to_text(message.get("content")), finish_reason="stop" if body.get("done") else None, usage=usage)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc

    async def health_check(self) -> bool:
        response = await self._send("GET", f"{self._base_url()}/api/tags")
        return response.status_code == 200

class GeminiAdapter(ProviderAdapter):
    def _base_url(self) -> str:
        return (self.provider.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        contents = []
        system_parts = []
        for message in request.messages:
            content = _content_to_text(message.content)
            if message.role == "system":
                system_parts.append(content)
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": content}]})
        generation_config = {key: value for key, value in {"temperature": request.temperature, "topP": request.top_p, "maxOutputTokens": request.max_tokens or request.max_completion_tokens}.items() if value is not None}
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if generation_config:
            payload["generationConfig"] = generation_config
        api_key = self.credentials.get("api_key")
        response = await self._send("POST", f"{self._base_url()}/models/{self.model.model_name}:generateContent?key={api_key}", json=payload)
        body = response.json()
        candidate = (body.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        usage = body.get("usageMetadata") or {}
        return ProviderResponse(
            content="".join(part.get("text", "") for part in parts),
            usage=_usage({"prompt_tokens": usage.get("promptTokenCount", 0), "completion_tokens": usage.get("candidatesTokenCount", 0)}),
            finish_reason=candidate.get("finishReason", "STOP").lower(),
            raw=body,
        )

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        contents = []
        system_parts = []
        for message in request.messages:
            content = _content_to_text(message.content)
            if message.role == "system":
                system_parts.append(content)
                continue
            contents.append({"role": "model" if message.role == "assistant" else "user", "parts": [{"text": content}]})
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        generation_config = {key: value for key, value in {"temperature": request.temperature, "topP": request.top_p, "maxOutputTokens": request.max_tokens or request.max_completion_tokens}.items() if value is not None}
        if generation_config:
            payload["generationConfig"] = generation_config
        api_key = self.credentials.get("api_key")
        url = f"{self._base_url()}/models/{self.model.model_name}:streamGenerateContent?alt=sse&key={api_key}"
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    await _ensure_stream_response(response)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            body = json.loads(line.removeprefix("data:").strip())
                        except json.JSONDecodeError:
                            continue
                        candidate = (body.get("candidates") or [{}])[0]
                        parts = (candidate.get("content") or {}).get("parts") or []
                        usage_data = body.get("usageMetadata") or {}
                        usage = _usage({"prompt_tokens": usage_data.get("promptTokenCount", 0), "completion_tokens": usage_data.get("candidatesTokenCount", 0)}) if usage_data else None
                        yield ProviderStreamChunk(delta="".join(part.get("text", "") for part in parts), finish_reason=(candidate.get("finishReason") or "").lower() or None, usage=usage)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc

    async def health_check(self) -> bool:
        api_key = self.credentials.get("api_key")
        response = await self._send("GET", f"{self._base_url()}/models?key={api_key}")
        return response.status_code == 200

def adapter_for(provider: Provider, model: ModelRecord) -> ProviderAdapter:
    adapters = {
        "openai": OpenAIAdapter,
        "groq": GroqAdapter,
        "ollama": OllamaAdapter,
        "gemini": GeminiAdapter,
        "openai_compatible": OpenAICompatibleAdapter,
    }
    try:
        return adapters[provider.provider_type](provider, model)
    except KeyError as exc:
        raise ProviderError(500, "unsupported_provider", f"Unsupported provider type: {provider.provider_type}") from exc
