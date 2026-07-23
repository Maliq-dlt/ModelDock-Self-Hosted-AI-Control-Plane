import json
import re
from typing import Any

from app.schemas import ChatCompletionRequest, Message

ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
CAVEMAN_INSTRUCTION = (
    "Answer concise. Remove filler, pleasantries, and repetition. "
    "Preserve technical detail, code, paths, commands, errors, warnings, dates, and requested output. "
    "Never omit required content."
)
PONYTAIL_INSTRUCTION = (
    "For coding tasks, choose smallest sufficient change: YAGNI, stdlib/native first, existing dependency before new dependency. "
    "Preserve validation, error handling, security, accessibility, and requested behavior. "
    "State deliberate simplifications and upgrade ceiling."
)


def _rough_tokens(messages: list[Message]) -> int:
    return max(1, sum(len(str(message.content or "")) for message in messages) // 4)


def _compact_tool_text(content: str) -> str:
    normalized = ANSI_ESCAPE.sub("", content.replace("\r\n", "\n").replace("\r", "\n"))
    try:
        parsed: Any = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return normalized


def _append_instruction(messages: list[Message], instruction: str) -> list[Message]:
    updated = [message.model_copy(deep=True) for message in messages]
    system_index = next((index for index, message in enumerate(updated) if message.role == "system"), None)
    if system_index is None:
        return [Message(role="system", content=instruction), *updated]
    current = str(updated[system_index].content or "")
    if instruction not in current:
        updated[system_index] = updated[system_index].model_copy(update={"content": f"{current}\n\n{instruction}".strip()})
    return updated



def mode_from_policy(policy: dict[str, Any] | None) -> str:
    policy = policy or {}
    caveman = bool(policy.get("caveman"))
    ponytail = bool(policy.get("ponytail"))
    if caveman and ponytail:
        return "stacked"
    if caveman:
        return "caveman"
    if ponytail:
        return "ponytail"
    return "safe" if policy.get("safe") else "off"

def optimize_request(request: ChatCompletionRequest) -> tuple[ChatCompletionRequest, dict[str, Any]]:
    mode = request.modeldock.token_mode
    before_tokens = _rough_tokens(request.messages)
    if mode == "off":
        return request, {
            "mode": mode,
            "lossless_input": True,
            "output_transform": "none",
            "input_tokens_before": before_tokens,
            "input_tokens_after": before_tokens,
            "input_tokens_saved": 0,
        }

    messages: list[Message] = []
    compacted_messages = 0
    for message in request.messages:
        current = message.model_copy(deep=True)
        if current.role == "tool" and isinstance(current.content, str):
            compacted = _compact_tool_text(current.content)
            if compacted != current.content:
                compacted_messages += 1
                current.content = compacted
        messages.append(current)

    if mode in {"caveman", "stacked"}:
        messages = _append_instruction(messages, CAVEMAN_INSTRUCTION)
    if mode in {"ponytail", "stacked"}:
        messages = _append_instruction(messages, PONYTAIL_INSTRUCTION)

    after_tokens = _rough_tokens(messages)
    stats = {
        "mode": mode,
        "lossless_input": True,
        "output_transform": "none",
        "input_tokens_before": before_tokens,
        "input_tokens_after": after_tokens,
        "input_tokens_saved": max(0, before_tokens - after_tokens),
        "input_token_delta": after_tokens - before_tokens,
        "compacted_tool_messages": compacted_messages,
    }
    # ponytail: safe ceiling = formatting/JSON compaction only; add retrieval-backed chunking after context store + tool contract.
    metadata = {**request.metadata, "modeldock_token_efficiency": stats}
    optimized = request.model_copy(deep=True, update={"messages": messages, "metadata": metadata})
    return optimized, stats
