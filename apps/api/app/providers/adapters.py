import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable

import httpx

from app.core.security import decrypt_credentials
from app.models import ModelRecord, Provider, ProviderAccount
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


@dataclass
class ProviderModel:
    model_name: str
    display_name: str | None = None
    context_window: int = 8192
    capabilities: list[str] | None = None
    pricing: dict[str, float] | None = None


@runtime_checkable
class ProviderAdapterProtocol(Protocol):
    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse: ...

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]: ...

    async def health_check(self) -> bool: ...

    async def list_models(self) -> list[ProviderModel]: ...


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


def _model_list(body: dict[str, Any], owned_by: str | None = None) -> list[ProviderModel]:
    models = body.get("data") or body.get("models") or []
    result = []
    for item in models:
        if isinstance(item, str):
            result.append(ProviderModel(model_name=item, display_name=item, capabilities=["chat"]))
            continue
        name = item.get("id") or item.get("name")
        if not name:
            continue
        result.append(
            ProviderModel(
                model_name=str(name).removeprefix("models/"),
                display_name=item.get("display_name") or item.get("displayName") or str(name),
                context_window=int(item.get("context_window") or item.get("inputTokenLimit") or 8192),
                capabilities=["chat"],
            )
        )
    return result


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
    def __init__(self, provider: Provider, model: ModelRecord, account: ProviderAccount | None = None) -> None:
        self.provider = provider
        self.model = model
        self.account = account
        encrypted_credentials = account.encrypted_credentials if account else provider.encrypted_credentials
        self.credentials = decrypt_credentials(encrypted_credentials)

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        raise NotImplementedError

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        response = await self.chat(request)
        yield ProviderStreamChunk(delta=response.content, finish_reason=response.finish_reason, usage=response.usage)

    async def health_check(self) -> bool:
        raise NotImplementedError

    async def list_models(self) -> list[ProviderModel]:
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
        payload = request.model_dump(exclude_none=True, exclude={"task_type", "data_classification", "metadata", "modeldock"})
        payload["model"] = self.model.model_name
        payload["stream"] = False
        response = await self._send("POST", self._openai_url(), json=payload, headers=self._auth_headers())
        body = response.json()
        choice = (body.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return ProviderResponse(content=_content_to_text(message.get("content")), usage=_usage(body.get("usage")), finish_reason=choice.get("finish_reason") or "stop", raw=body, tool_calls=message.get("tool_calls"))

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        payload = request.model_dump(exclude_none=True, exclude={"task_type", "data_classification", "metadata", "modeldock"})
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

    async def list_models(self) -> list[ProviderModel]:
        response = await self._send("GET", f"{self._base_url()}/models", headers=self._auth_headers())
        return _model_list(response.json())


class OpenAIResponsesAdapter(OpenAIAdapter):
    def _responses_url(self) -> str:
        return f"{self._base_url()}/responses"

    def _responses_payload(self, request: ChatCompletionRequest, stream: bool) -> dict[str, Any]:
        system_parts = []
        input_items = []
        for message in request.messages:
            content = _content_to_text(message.content)
            if message.role == "system":
                system_parts.append(content)
                continue
            if message.role == "tool":
                input_items.append({"type": "function_call_output", "call_id": message.tool_call_id, "output": content})
                continue
            if content:
                input_items.append({"role": message.role, "content": [{"type": "input_text", "text": content}]})
            for tool_call in message.tool_calls or []:
                function = tool_call.get("function") or {}
                input_items.append({"type": "function_call", "call_id": tool_call.get("id"), "name": function.get("name"), "arguments": function.get("arguments") or "{}"})
        payload: dict[str, Any] = {"model": self.model.model_name, "input": input_items, "stream": stream}
        if system_parts:
            payload["instructions"] = "\n\n".join(system_parts)
        for key, value in (("temperature", request.temperature), ("top_p", request.top_p), ("max_output_tokens", request.max_tokens or request.max_completion_tokens)):
            if value is not None:
                payload[key] = value
        if request.tools:
            payload["tools"] = []
            for item in request.tools:
                function = item.get("function") or {}
                tool = {"type": "function", "name": function.get("name"), "parameters": function.get("parameters") or {}}
                if function.get("description"):
                    tool["description"] = function["description"]
                if "strict" in function:
                    tool["strict"] = function["strict"]
                payload["tools"].append(tool)
        if request.tool_choice:
            if isinstance(request.tool_choice, dict) and request.tool_choice.get("function"):
                payload["tool_choice"] = {"type": "function", "name": request.tool_choice["function"]["name"]}
            else:
                payload["tool_choice"] = request.tool_choice
        return payload

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        response = await self._send("POST", self._responses_url(), json=self._responses_payload(request, False), headers=self._auth_headers())
        body = response.json()
        tool_calls = []
        for item in body.get("output") or []:
            if item.get("type") == "function_call":
                tool_calls.append({"id": item.get("call_id") or item.get("id"), "type": "function", "function": {"name": item.get("name"), "arguments": item.get("arguments") or "{}"}})
        text = body.get("output_text") or ""
        if not text:
            text = "".join(block.get("text", "") for item in body.get("output") or [] for block in item.get("content") or [] if block.get("type") in {"output_text", "text"})
        return ProviderResponse(content=text, usage=_usage(body.get("usage")), finish_reason="stop", raw=body, tool_calls=tool_calls or None)

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", self._responses_url(), json=self._responses_payload(request, True), headers=self._auth_headers()) as response:
                    await _ensure_stream_response(response)
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        try:
                            body = json.loads(line.removeprefix("data:").strip())
                        except json.JSONDecodeError:
                            continue
                        event_type = body.get("type")
                        if event_type == "response.output_text.delta":
                            yield ProviderStreamChunk(delta=body.get("delta") or "")
                        elif event_type == "response.completed":
                            response_body = body.get("response") or {}
                            yield ProviderStreamChunk(finish_reason="stop", usage=_usage(response_body.get("usage")))
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc


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
        return ProviderResponse(content=_content_to_text((body.get("message") or {}).get("content")), usage=_usage({"prompt_tokens": body.get("prompt_eval_count", 0), "completion_tokens": body.get("eval_count", 0)}), finish_reason="stop", raw=body)

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
                        usage = _usage({"prompt_tokens": body.get("prompt_eval_count", 0), "completion_tokens": body.get("eval_count", 0)}) if body.get("done") else None
                        yield ProviderStreamChunk(delta=_content_to_text(message.get("content")), finish_reason="stop" if body.get("done") else None, usage=usage)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc

    async def health_check(self) -> bool:
        response = await self._send("GET", f"{self._base_url()}/api/tags")
        return response.status_code == 200

    async def list_models(self) -> list[ProviderModel]:
        response = await self._send("GET", f"{self._base_url()}/api/tags")
        return _model_list(response.json())


class GeminiAdapter(ProviderAdapter):
    def _base_url(self) -> str:
        return (self.provider.base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")

    def _generation_config(self, request: ChatCompletionRequest) -> dict[str, Any]:
        return {key: value for key, value in {"temperature": request.temperature, "topP": request.top_p, "maxOutputTokens": request.max_tokens or request.max_completion_tokens}.items() if value is not None}

    def _payload(self, request: ChatCompletionRequest) -> dict[str, Any]:
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
        generation_config = self._generation_config(request)
        if generation_config:
            payload["generationConfig"] = generation_config
        return payload

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        api_key = self.credentials.get("api_key")
        response = await self._send("POST", f"{self._base_url()}/models/{self.model.model_name}:generateContent?key={api_key}", json=self._payload(request))
        body = response.json()
        candidate = (body.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        usage = body.get("usageMetadata") or {}
        return ProviderResponse(content="".join(part.get("text", "") for part in parts), usage=_usage({"prompt_tokens": usage.get("promptTokenCount", 0), "completion_tokens": usage.get("candidatesTokenCount", 0)}), finish_reason=candidate.get("finishReason", "STOP").lower(), raw=body)

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        api_key = self.credentials.get("api_key")
        url = f"{self._base_url()}/models/{self.model.model_name}:streamGenerateContent?alt=sse&key={api_key}"
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", url, json=self._payload(request)) as response:
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

    async def list_models(self) -> list[ProviderModel]:
        api_key = self.credentials.get("api_key")
        response = await self._send("GET", f"{self._base_url()}/models?key={api_key}")
        return _model_list(response.json())


class AnthropicAdapter(ProviderAdapter):
    def _base_url(self) -> str:
        return (self.provider.base_url or "https://api.anthropic.com/v1").rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        headers = {str(key): str(value) for key, value in (self.credentials.get("headers") or {}).items()}
        api_key = self.credentials.get("api_key")
        if api_key:
            headers.setdefault("x-api-key", api_key)
        headers.setdefault("anthropic-version", self.credentials.get("anthropic_version", "2023-06-01"))
        headers.setdefault("content-type", "application/json")
        return headers

    def _payload(self, request: ChatCompletionRequest, stream: bool) -> dict[str, Any]:
        system_parts = []
        messages = []
        for message in request.messages:
            content = _content_to_text(message.content)
            if message.role == "system":
                system_parts.append(content)
                continue
            if message.role == "tool":
                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": message.tool_call_id, "content": content}]})
                continue
            blocks: list[dict[str, Any]] = []
            if content:
                blocks.append({"type": "text", "text": content})
            for tool_call in message.tool_calls or []:
                function = tool_call.get("function") or {}
                try:
                    tool_input = json.loads(function.get("arguments") or "{}")
                except json.JSONDecodeError:
                    tool_input = {"raw": function.get("arguments") or ""}
                blocks.append({"type": "tool_use", "id": tool_call.get("id"), "name": function.get("name"), "input": tool_input})
            messages.append({"role": message.role, "content": blocks or [{"type": "text", "text": ""}]})
        payload: dict[str, Any] = {"model": self.model.model_name, "messages": messages, "max_tokens": request.max_tokens or request.max_completion_tokens or 1024, "stream": stream}
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.top_p is not None:
            payload["top_p"] = request.top_p
        if request.stop is not None:
            payload["stop_sequences"] = request.stop if isinstance(request.stop, list) else [request.stop]
        if request.tools:
            payload["tools"] = [{"name": item.get("function", {}).get("name"), "description": item.get("function", {}).get("description"), "input_schema": item.get("function", {}).get("parameters", {})} for item in request.tools]
        if request.tool_choice:
            if isinstance(request.tool_choice, dict) and request.tool_choice.get("function"):
                payload["tool_choice"] = {"type": "tool", "name": request.tool_choice["function"]["name"]}
            elif request.tool_choice == "required":
                payload["tool_choice"] = {"type": "any"}
            elif request.tool_choice != "none":
                payload["tool_choice"] = {"type": request.tool_choice}
        return payload

    async def chat(self, request: ChatCompletionRequest) -> ProviderResponse:
        response = await self._send("POST", f"{self._base_url()}/messages", json=self._payload(request, False), headers=self._auth_headers())
        body = response.json()
        text_parts = []
        tool_calls = []
        for block in body.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({"id": block.get("id"), "type": "function", "function": {"name": block.get("name"), "arguments": json.dumps(block.get("input") or {}, separators=(",", ":"))}})
        return ProviderResponse(content="".join(text_parts), usage=_usage({"input_tokens": (body.get("usage") or {}).get("input_tokens", 0), "output_tokens": (body.get("usage") or {}).get("output_tokens", 0)}), finish_reason=body.get("stop_reason") or "end_turn", raw=body, tool_calls=tool_calls or None)

    async def stream_chat(self, request: ChatCompletionRequest) -> AsyncIterator[ProviderStreamChunk]:
        async with httpx.AsyncClient(timeout=self.provider.timeout_seconds) as client:
            try:
                async with client.stream("POST", f"{self._base_url()}/messages", json=self._payload(request, True), headers=self._auth_headers()) as response:
                    await _ensure_stream_response(response)
                    event_type = ""
                    async for line in response.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line.removeprefix("event:").strip()
                            continue
                        if not line.startswith("data:"):
                            continue
                        try:
                            body = json.loads(line.removeprefix("data:").strip())
                        except json.JSONDecodeError:
                            continue
                        kind = body.get("type") or event_type
                        if kind == "content_block_delta":
                            delta = (body.get("delta") or {}).get("text") or ""
                            yield ProviderStreamChunk(delta=delta)
                        elif kind == "message_delta":
                            usage = _usage({"input_tokens": 0, "output_tokens": (body.get("usage") or {}).get("output_tokens", 0)})
                            yield ProviderStreamChunk(finish_reason=(body.get("delta") or {}).get("stop_reason"), usage=usage)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                raise ProviderError(503, "network_error", str(exc), retryable=True) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(502, "provider_http_error", str(exc), retryable=True) from exc

    async def health_check(self) -> bool:
        response = await self._send("GET", f"{self._base_url()}/models", headers=self._auth_headers())
        return response.status_code == 200

    async def list_models(self) -> list[ProviderModel]:
        response = await self._send("GET", f"{self._base_url()}/models", headers=self._auth_headers())
        return _model_list(response.json())


AdapterFactory = Callable[[Provider, ModelRecord, ProviderAccount | None], ProviderAdapter]
_ADAPTERS: dict[str, AdapterFactory] = {}


def register_adapter(provider_type: str, factory: AdapterFactory, *, replace: bool = False) -> None:
    if provider_type in _ADAPTERS and not replace:
        raise ValueError(f"Adapter already registered: {provider_type}")
    _ADAPTERS[provider_type] = factory


def adapter_for(provider: Provider, model: ModelRecord, account: ProviderAccount | None = None) -> ProviderAdapter:
    try:
        factory = _ADAPTERS[provider.provider_type]
    except KeyError as exc:
        raise ProviderError(500, "unsupported_provider", f"Unsupported provider type: {provider.provider_type}") from exc
    return factory(provider, model, account)


for _provider_type, _adapter in {
    "openai": OpenAIAdapter,
    "openai_responses": OpenAIResponsesAdapter,
    "anthropic": AnthropicAdapter,
    "groq": GroqAdapter,
    "ollama": OllamaAdapter,
    "gemini": GeminiAdapter,
    "openai_compatible": OpenAICompatibleAdapter,
}.items():
    register_adapter(_provider_type, _adapter)
