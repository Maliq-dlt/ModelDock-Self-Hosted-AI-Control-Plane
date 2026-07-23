import json
import time
from typing import Any, Literal
from uuid import uuid4

from app.providers.adapters import ProviderResponse
from app.schemas import AnthropicMessagesRequest, ChatCompletionRequest, Message, ResponsesRequest

ProtocolName = Literal["openai", "responses", "anthropic"]


def _text_content(value: str | list[dict[str, Any]] | None) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    parts = []
    for block in value:
        block_type = block.get("type")
        if block_type in {"text", "input_text", "output_text"}:
            parts.append(str(block.get("text", "")))
        else:
            raise ValueError(f"Unsupported content block type: {block_type}")
    return "".join(parts)


def _chat_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    converted = []
    for tool in tools:
        if tool.get("type") != "function":
            raise ValueError(f"Unsupported tool type: {tool.get('type')}")
        if "function" in tool:
            converted.append(tool)
        else:
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description"),
                        "parameters": tool.get("parameters") or tool.get("input_schema") or {},
                    },
                }
            )
    return converted


def _chat_tool_choice(value: str | dict[str, Any] | None) -> str | dict[str, Any] | None:
    if not isinstance(value, dict) or "function" in value:
        return value
    choice_type = value.get("type")
    if choice_type in {"auto", "any", "none"}:
        return "required" if choice_type == "any" else choice_type
    if choice_type == "tool" and value.get("name"):
        return {"type": "function", "function": {"name": value["name"]}}
    return value


def responses_to_chat(request: ResponsesRequest) -> ChatCompletionRequest:
    messages: list[Message] = []
    if request.instructions:
        messages.append(Message(role="system", content=request.instructions))
    if isinstance(request.input, str):
        messages.append(Message(role="user", content=request.input))
    else:
        for item in request.input:
            item_type = item.get("type")
            if item_type == "function_call":
                messages.append(
                    Message(
                        role="assistant",
                        tool_calls=[
                            {
                                "id": item.get("call_id") or item.get("id") or f"call_{uuid4().hex}",
                                "type": "function",
                                "function": {
                                    "name": item.get("name"),
                                    "arguments": item.get("arguments") or "{}",
                                },
                            }
                        ],
                    )
                )
                continue
            if item_type == "function_call_output":
                messages.append(
                    Message(
                        role="tool",
                        tool_call_id=str(item.get("call_id") or ""),
                        content=str(item.get("output") or ""),
                    )
                )
                continue
            role = item.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                raise ValueError(f"Unsupported response input item type: {item_type}")
            messages.append(
                Message(
                    role=role,
                    content=_text_content(item.get("content")),
                    tool_call_id=item.get("tool_call_id"),
                )
            )
    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
        top_p=request.top_p,
        max_completion_tokens=request.max_output_tokens,
        tools=_chat_tools(request.tools),
        tool_choice=_chat_tool_choice(request.tool_choice),
        stream=request.stream,
        metadata={**request.metadata, "modeldock_protocol": "responses"},
        modeldock=request.modeldock,
    )


def anthropic_to_chat(request: AnthropicMessagesRequest) -> ChatCompletionRequest:
    messages: list[Message] = []
    if request.system:
        messages.append(Message(role="system", content=_text_content(request.system)))
    for source in request.messages:
        if isinstance(source.content, str):
            messages.append(Message(role=source.role, content=source.content))
            continue
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[Message] = []
        for block in source.content:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(str(block.get("text", "")))
            elif block_type == "tool_use" and source.role == "assistant":
                tool_calls.append(
                    {
                        "id": block.get("id") or f"toolu_{uuid4().hex}",
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input") or {}, separators=(",", ":")),
                        },
                    }
                )
            elif block_type == "tool_result" and source.role == "user":
                tool_results.append(
                    Message(
                        role="tool",
                        tool_call_id=str(block.get("tool_use_id") or ""),
                        content=_text_content(block.get("content")),
                    )
                )
            else:
                raise ValueError(f"Unsupported Anthropic content block type: {block_type}")
        if text_parts or tool_calls:
            messages.append(
                Message(
                    role=source.role,
                    content="".join(text_parts) or None,
                    tool_calls=tool_calls or None,
                )
            )
        messages.extend(tool_results)
    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
        top_p=request.top_p,
        max_completion_tokens=request.max_tokens,
        stop=request.stop_sequences,
        tools=_chat_tools(request.tools),
        tool_choice=_chat_tool_choice(request.tool_choice),
        stream=request.stream,
        metadata={**request.metadata, "modeldock_protocol": "anthropic"},
        modeldock=request.modeldock,
    )


def response_id(protocol: ProtocolName) -> str:
    prefix = {"openai": "chatcmpl", "responses": "resp", "anthropic": "msg"}[protocol]
    return f"{prefix}_{uuid4().hex}"


def format_response(
    protocol: ProtocolName,
    request: ChatCompletionRequest,
    result: ProviderResponse,
    trace_id: str,
    item_id: str | None = None,
) -> dict[str, Any]:
    item_id = item_id or response_id(protocol)
    usage = result.usage
    if protocol == "responses":
        output: list[dict[str, Any]] = []
        if result.content:
            output.append(
                {
                    "id": f"msg_{uuid4().hex}",
                    "type": "message",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": result.content, "annotations": []}],
                }
            )
        for tool_call in result.tool_calls or []:
            function = tool_call.get("function") or {}
            output.append(
                {
                    "id": tool_call.get("id") or f"fc_{uuid4().hex}",
                    "type": "function_call",
                    "call_id": tool_call.get("id") or f"call_{uuid4().hex}",
                    "name": function.get("name"),
                    "arguments": function.get("arguments") or "{}",
                    "status": "completed",
                }
            )
        return {
            "id": item_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "completed",
            "model": request.model,
            "output": output,
            "output_text": result.content,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "modeldock": {"trace_id": trace_id},
        }
    if protocol == "anthropic":
        content: list[dict[str, Any]] = []
        if result.content:
            content.append({"type": "text", "text": result.content})
        for tool_call in result.tool_calls or []:
            function = tool_call.get("function") or {}
            try:
                tool_input = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                tool_input = {"raw": function.get("arguments") or ""}
            content.append(
                {
                    "type": "tool_use",
                    "id": tool_call.get("id") or f"toolu_{uuid4().hex}",
                    "name": function.get("name"),
                    "input": tool_input,
                }
            )
        stop_reason = "tool_use" if result.tool_calls else {
            "length": "max_tokens",
            "stop": "end_turn",
        }.get(result.finish_reason, result.finish_reason or "end_turn")
        return {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "model": request.model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            "modeldock": {"trace_id": trace_id},
        }
    message: dict[str, Any] = {
        "role": "assistant",
        "content": None if result.tool_calls and not result.content else result.content,
    }
    if result.tool_calls:
        message["tool_calls"] = result.tool_calls
    return {
        "id": item_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "message": message, "finish_reason": result.finish_reason}],
        "usage": usage,
        "modeldock": {"trace_id": trace_id},
    }


def _sse(data: dict[str, Any], event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, separators=(',', ':'))}\n\n"


def stream_start(protocol: ProtocolName, item_id: str, request: ChatCompletionRequest, trace_id: str) -> list[str]:
    if protocol == "responses":
        body = {
            "id": item_id,
            "object": "response",
            "created_at": int(time.time()),
            "status": "in_progress",
            "model": request.model,
            "output": [],
            "modeldock": {"trace_id": trace_id},
        }
        return [_sse({"type": "response.created", "response": body})]
    if protocol == "anthropic":
        body = {
            "type": "message_start",
            "message": {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "model": request.model,
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "modeldock": {"trace_id": trace_id},
            },
        }
        return [_sse(body, "message_start"), _sse({"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, "content_block_start")]
    return []


def stream_delta(protocol: ProtocolName, item_id: str, request: ChatCompletionRequest, trace_id: str, delta: str) -> list[str]:
    if protocol == "responses":
        return [_sse({"type": "response.output_text.delta", "response_id": item_id, "output_index": 0, "content_index": 0, "delta": delta})]
    if protocol == "anthropic":
        return [_sse({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": delta}}, "content_block_delta")]
    body = {
        "id": item_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        "modeldock": {"trace_id": trace_id},
    }
    return [_sse(body)]


def stream_complete(
    protocol: ProtocolName,
    item_id: str,
    request: ChatCompletionRequest,
    trace_id: str,
    content: str,
    usage: dict[str, int],
) -> list[str]:
    result = ProviderResponse(content=content, usage=usage, finish_reason="stop", raw={})
    if protocol == "responses":
        body = format_response(protocol, request, result, trace_id, item_id)
        return [
            _sse({"type": "response.output_text.done", "response_id": item_id, "output_index": 0, "content_index": 0, "text": content}),
            _sse({"type": "response.completed", "response": body}),
        ]
    if protocol == "anthropic":
        return [
            _sse({"type": "content_block_stop", "index": 0}, "content_block_stop"),
            _sse({"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None}, "usage": {"output_tokens": usage.get("completion_tokens", 0)}}, "message_delta"),
            _sse({"type": "message_stop"}, "message_stop"),
        ]
    body = {
        "id": item_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        "usage": usage,
        "modeldock": {"trace_id": trace_id},
    }
    return [_sse(body), "data: [DONE]\n\n"]


def format_error(protocol: ProtocolName, error_type: str, message: str, trace_id: str | None = None) -> dict[str, Any]:
    if protocol == "anthropic":
        body: dict[str, Any] = {"type": "error", "error": {"type": error_type, "message": message}}
    else:
        body = {"error": {"message": message, "type": error_type, "code": error_type}}
    if trace_id:
        body["modeldock"] = {"trace_id": trace_id}
    return body


def stream_replay(
    protocol: ProtocolName,
    request: ChatCompletionRequest,
    replay: dict[str, Any],
    trace_id: str,
) -> list[str]:
    if protocol == "responses":
        content = str(replay.get("output_text") or "")
        source_usage = replay.get("usage") or {}
        usage = _usage_from_protocol(source_usage)
        item_id = str(replay.get("id") or response_id(protocol))
    elif protocol == "anthropic":
        content = "".join(block.get("text", "") for block in replay.get("content") or [] if block.get("type") == "text")
        source_usage = replay.get("usage") or {}
        usage = _usage_from_protocol(source_usage)
        item_id = str(replay.get("id") or response_id(protocol))
    else:
        message = ((replay.get("choices") or [{}])[0].get("message") or {})
        content = str(message.get("content") or "")
        usage = _usage_from_protocol(replay.get("usage") or {})
        item_id = str(replay.get("id") or response_id(protocol))
    return [*stream_start(protocol, item_id, request, trace_id), *stream_delta(protocol, item_id, request, trace_id, content), *stream_complete(protocol, item_id, request, trace_id, content, usage)]


def _usage_from_protocol(value: dict[str, Any]) -> dict[str, int]:
    prompt = int(value.get("prompt_tokens", value.get("input_tokens", 0)) or 0)
    completion = int(value.get("completion_tokens", value.get("output_tokens", 0)) or 0)
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": int(value.get("total_tokens") or prompt + completion)}


def stream_error(protocol: ProtocolName, error_type: str, message: str, trace_id: str) -> str:
    return _sse(format_error(protocol, error_type, message, trace_id), "error" if protocol == "anthropic" else None)
