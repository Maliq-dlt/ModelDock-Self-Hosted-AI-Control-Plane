import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import request_slot
from app.core.config import get_settings
from app.models import APIKey, Budget, Environment, ModelRecord, RequestAttempt, RequestRecord
from app.providers.adapters import ProviderError, ProviderResponse, adapter_for
from app.routing.engine import resolve_route
from app.services.provider_health import record_provider_failure, record_provider_success
from app.schemas import ChatCompletionRequest


class BudgetExceeded(Exception):
    def __init__(self, trace_id: str, limit: float, spent: float) -> None:
        self.trace_id = trace_id
        self.limit = limit
        self.spent = spent
        super().__init__(f"Monthly budget exceeded: {spent:.6f} / {limit:.6f} USD")


class QuotaExceeded(Exception):
    def __init__(self, trace_id: str, limit: int, used: int) -> None:
        self.trace_id = trace_id
        self.limit = limit
        self.used = used
        super().__init__(f"Monthly token quota exceeded: {used} / {limit}")


def approximate_tokens(messages: list[Any]) -> int:
    text = " ".join(str(message.content or "") for message in messages)
    return max(1, len(text) // 4)


def estimate_cost(model: ModelRecord, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = model.pricing_json or {}
    input_rate = float(pricing.get("input_cost_per_million", 0))
    output_rate = float(pricing.get("output_cost_per_million", 0))
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000


def month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def current_project_spend(session: AsyncSession, project_id: str) -> float:
    value = await session.scalar(
        select(func.coalesce(func.sum(RequestRecord.estimated_cost), 0.0)).where(
            RequestRecord.project_id == project_id,
            RequestRecord.status == "success",
            RequestRecord.completed_at >= month_start(datetime.now(timezone.utc)),
        )
    )
    return float(value or 0.0)


async def current_key_tokens(session: AsyncSession, api_key_id: str) -> int:
    value = await session.scalar(
        select(func.coalesce(func.sum(RequestRecord.total_tokens), 0)).where(
            RequestRecord.api_key_id == api_key_id,
            RequestRecord.status == "success",
            RequestRecord.completed_at >= month_start(datetime.now(timezone.utc)),
        )
    )
    return int(value or 0)


async def enforce_budget(session: AsyncSession, project_id: str, trace_id: str) -> None:
    budget = await session.scalar(
        select(Budget).where(
            Budget.scope_type == "project",
            Budget.scope_id == project_id,
            Budget.period == "monthly",
        )
    )
    if not budget or budget.action_at_limit != "block":
        return
    spent = await current_project_spend(session, project_id)
    if spent >= budget.limit_amount:
        raise BudgetExceeded(trace_id, budget.limit_amount, spent)


async def enforce_key_policy(
    session: AsyncSession,
    api_key: APIKey,
    request: ChatCompletionRequest,
    prompt_tokens: int,
    trace_id: str,
) -> None:
    if api_key.allowed_models_json and request.model not in api_key.allowed_models_json:
        raise HTTPException(status_code=403, detail="API key cannot use requested model")
    if api_key.token_limit_monthly:
        used = await current_key_tokens(session, api_key.id)
        if used + prompt_tokens > api_key.token_limit_monthly:
            raise QuotaExceeded(trace_id, api_key.token_limit_monthly, used)


def openai_response(
    request: ChatCompletionRequest,
    result: ProviderResponse,
    trace_id: str,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": None if result.tool_calls and not result.content else result.content,
    }
    if result.tool_calls:
        message["tool_calls"] = result.tool_calls
    return {
        "id": f"chatcmpl-{uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": result.usage,
        "modeldock": {"trace_id": trace_id},
    }


async def _idempotent_replay(
    session: AsyncSession,
    api_key_id: str,
    idempotency_key: str | None,
) -> tuple[dict[str, Any], str] | None:
    if not idempotency_key:
        return None
    existing = await session.scalar(
        select(RequestRecord).where(
            RequestRecord.api_key_id == api_key_id,
            RequestRecord.idempotency_key == idempotency_key,
        )
    )
    if not existing:
        return None
    response = (existing.metadata_json or {}).get("idempotency_response")
    if existing.status == "success" and response:
        return response, existing.trace_id
    error = ProviderError(
        409,
        "idempotency_conflict",
        "Request with this Idempotency-Key is already in progress or failed",
    )
    error.trace_id = existing.trace_id
    raise error


async def execute_chat(
    session: AsyncSession,
    api_key: APIKey,
    request: ChatCompletionRequest,
    idempotency_key: str | None = None,
) -> tuple[dict[str, Any], str]:
    replay = await _idempotent_replay(session, api_key.id, idempotency_key)
    if replay:
        return replay
    trace_id = f"trc_{uuid4().hex[:24]}"
    if not await session.get(Environment, api_key.environment_id):
        raise RuntimeError("API key environment not found")
    prompt_tokens = approximate_tokens(request.messages)
    settings = get_settings()
    initial_metadata: dict[str, Any] = {}
    if settings.log_payloads:
        initial_metadata["request"] = request.model_dump(mode="json", exclude_none=True)
    request_record = RequestRecord(
        trace_id=trace_id,
        project_id=api_key.project_id,
        environment_id=api_key.environment_id,
        api_key_id=api_key.id,
        virtual_model=request.model,
        idempotency_key=idempotency_key,
        status="pending",
        metadata_json=initial_metadata,
    )
    session.add(request_record)
    await session.flush()
    try:
        await enforce_budget(session, api_key.project_id, trace_id)
        await enforce_key_policy(session, api_key, request, prompt_tokens, trace_id)
    except (BudgetExceeded, QuotaExceeded) as exc:
        request_record.status = "blocked"
        request_record.completed_at = datetime.now(timezone.utc)
        error_type = "budget_exceeded" if isinstance(exc, BudgetExceeded) else "quota_exceeded"
        request_record.metadata_json = {
            **initial_metadata,
            "error": {"type": error_type, "message": str(exc)},
        }
        await session.commit()
        raise

    route_context = {
        "task_type": request.task_type,
        "data_classification": request.data_classification,
        "estimated_prompt_tokens": prompt_tokens,
        "metadata": request.metadata,
    }
    candidates, decision = await resolve_route(
        session,
        api_key.project_id,
        request.model,
        route_context,
    )
    request_record.metadata_json = {**initial_metadata, "routing_decision": decision}
    final_error: ProviderError | None = None
    attempt_number = 0
    started_request = time.perf_counter()

    for candidate in candidates:
        for retry_index in range(settings.max_retries_per_provider + 1):
            attempt_number += 1
            attempt = RequestAttempt(
                request_id=request_record.id,
                attempt_number=attempt_number,
                provider_id=candidate.provider.id,
                model_id=candidate.model.id,
                status="pending",
                prompt_tokens=prompt_tokens,
            )
            session.add(attempt)
            await session.flush()
            started = time.perf_counter()
            try:
                try:
                    async with request_slot(
                        f"provider:{candidate.provider.id}",
                        candidate.provider.concurrency_limit or 1,
                    ):
                        response = await adapter_for(candidate.provider, candidate.model).chat(request)
                except HTTPException as exc:
                    raise ProviderError(
                        exc.status_code,
                        "provider_concurrency_limit",
                        str(exc.detail),
                        retryable=True,
                    ) from exc
                latency_ms = (time.perf_counter() - started) * 1000
                record_provider_success(candidate.provider, latency_ms)
                response_prompt_tokens = response.usage.get("prompt_tokens") or prompt_tokens
                completion_tokens = response.usage.get("completion_tokens") or 0
                total_tokens = response.usage.get("total_tokens") or (
                    response_prompt_tokens + completion_tokens
                )
                cost = estimate_cost(
                    candidate.model,
                    response_prompt_tokens,
                    completion_tokens,
                )
                attempt.status = "success"
                attempt.latency_ms = latency_ms
                attempt.prompt_tokens = response_prompt_tokens
                attempt.completion_tokens = completion_tokens
                attempt.estimated_cost = cost
                attempt.completed_at = datetime.now(timezone.utc)
                request_record.status = "success"
                request_record.selected_model_id = candidate.model.id
                request_record.provider_id = candidate.provider.id
                request_record.prompt_tokens = response_prompt_tokens
                request_record.completion_tokens = completion_tokens
                request_record.total_tokens = total_tokens
                request_record.estimated_cost = cost
                request_record.latency_ms = (time.perf_counter() - started_request) * 1000
                request_record.completed_at = datetime.now(timezone.utc)
                response_body = openai_response(request, response, trace_id)
                response_metadata = (
                    {"content": response.content, "tool_calls": response.tool_calls}
                    if settings.log_payloads
                    else {}
                )
                request_record.metadata_json = {
                    **initial_metadata,
                    **decision,
                    "selected": {
                        "provider": candidate.provider.name,
                        "model": candidate.model.model_name,
                    },
                    **({"response": response_metadata} if response_metadata else {}),
                    **({"idempotency_response": response_body} if idempotency_key else {}),
                }
                await session.commit()
                return response_body, trace_id
            except ProviderError as exc:
                latency_ms = (time.perf_counter() - started) * 1000
                if exc.retryable and exc.error_type != "provider_concurrency_limit":
                    record_provider_failure(candidate.provider, latency_ms)
                final_error = exc
                attempt.status = "error"
                attempt.error_type = exc.error_type
                attempt.error_message = exc.message[:1000]
                attempt.latency_ms = latency_ms
                attempt.completed_at = datetime.now(timezone.utc)
                await session.flush()
                if not exc.retryable or retry_index >= settings.max_retries_per_provider:
                    break
                await asyncio.sleep(0.05 * (2**retry_index))

    request_record.status = "error"
    request_record.latency_ms = (time.perf_counter() - started_request) * 1000
    request_record.completed_at = datetime.now(timezone.utc)
    request_record.metadata_json = {
        **initial_metadata,
        **decision,
        "error": {
            "type": final_error.error_type if final_error else "provider_error",
            "message": final_error.message if final_error else "No provider succeeded",
        },
    }
    await session.commit()
    if final_error:
        final_error.trace_id = trace_id
        raise final_error
    error = ProviderError(
        503,
        "provider_unavailable",
        "No provider succeeded",
        retryable=False,
    )
    error.trace_id = trace_id
    raise error


async def prepare_stream_chat(
    session: AsyncSession,
    api_key: APIKey,
    request: ChatCompletionRequest,
    idempotency_key: str | None = None,
) -> tuple[str, dict[str, Any] | None, RequestRecord | None, list[Any], dict[str, Any], int]:
    replay = await _idempotent_replay(session, api_key.id, idempotency_key)
    if replay:
        return replay[1], replay[0], None, [], {}, 0
    trace_id = f"trc_{uuid4().hex[:24]}"
    if not await session.get(Environment, api_key.environment_id):
        raise RuntimeError("API key environment not found")
    prompt_tokens = approximate_tokens(request.messages)
    settings = get_settings()
    initial_metadata = {"request": request.model_dump(mode="json", exclude_none=True)} if settings.log_payloads else {}
    record = RequestRecord(
        trace_id=trace_id,
        project_id=api_key.project_id,
        environment_id=api_key.environment_id,
        api_key_id=api_key.id,
        virtual_model=request.model,
        idempotency_key=idempotency_key,
        status="pending",
        metadata_json=initial_metadata,
    )
    session.add(record)
    await session.flush()
    try:
        await enforce_budget(session, api_key.project_id, trace_id)
        await enforce_key_policy(session, api_key, request, prompt_tokens, trace_id)
    except (BudgetExceeded, QuotaExceeded) as exc:
        record.status = "blocked"
        record.completed_at = datetime.now(timezone.utc)
        record.metadata_json = {**initial_metadata, "error": {"type": "budget_exceeded" if isinstance(exc, BudgetExceeded) else "quota_exceeded", "message": str(exc)}}
        await session.commit()
        raise
    context = {"task_type": request.task_type, "data_classification": request.data_classification, "estimated_prompt_tokens": prompt_tokens, "metadata": request.metadata}
    candidates, decision = await resolve_route(session, api_key.project_id, request.model, context)
    record.metadata_json = {**initial_metadata, "routing_decision": decision}
    return trace_id, None, record, candidates, decision, prompt_tokens


def _stream_event(completion_id: str, request: ChatCompletionRequest, trace_id: str, delta: str = "", finish_reason: str | None = None, usage: dict[str, int] | None = None) -> str:
    payload: dict[str, Any] = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": request.model,
        "choices": [{"index": 0, "delta": {"content": delta} if delta else {}, "finish_reason": finish_reason}],
        "modeldock": {"trace_id": trace_id},
    }
    if usage is not None:
        payload["usage"] = usage
    return f'data: {json.dumps(payload, separators=(",", ":"))}\n\n'


async def stream_chat_events(
    session: AsyncSession,
    request: ChatCompletionRequest,
    trace_id: str,
    record: RequestRecord,
    candidates: list[Any],
    decision: dict[str, Any],
    prompt_tokens: int,
    idempotency_key: str | None = None,
) -> AsyncIterator[str]:
    completion_id = f"chatcmpl-{uuid4().hex}"
    attempt_number = 0
    started_request = time.perf_counter()
    settings = get_settings()
    final_error: ProviderError | None = None
    for candidate in candidates:
        for retry_index in range(settings.max_retries_per_provider + 1):
            attempt_number += 1
            attempt = RequestAttempt(request_id=record.id, attempt_number=attempt_number, provider_id=candidate.provider.id, model_id=candidate.model.id, status="pending", prompt_tokens=prompt_tokens)
            session.add(attempt)
            await session.flush()
            started = time.perf_counter()
            content_parts: list[str] = []
            usage = {"prompt_tokens": prompt_tokens, "completion_tokens": 0, "total_tokens": prompt_tokens}
            streamed = False
            try:
                try:
                    async with request_slot(
                        f"provider:{candidate.provider.id}",
                        candidate.provider.concurrency_limit or 1,
                    ):
                        async for chunk in adapter_for(candidate.provider, candidate.model).stream_chat(request):
                            streamed = True
                            content_parts.append(chunk.delta)
                            if chunk.usage:
                                usage = chunk.usage
                            yield _stream_event(completion_id, request, trace_id, chunk.delta)
                except HTTPException as exc:
                    raise ProviderError(
                        exc.status_code,
                        "provider_concurrency_limit",
                        str(exc.detail),
                        retryable=True,
                    ) from exc
                usage["completion_tokens"] = usage.get("completion_tokens", 0) or max(0, len("".join(content_parts)) // 4)
                usage["total_tokens"] = usage.get("total_tokens", 0) or usage["prompt_tokens"] + usage["completion_tokens"]
                latency_ms = (time.perf_counter() - started) * 1000
                record_provider_success(candidate.provider, latency_ms)
                cost = estimate_cost(candidate.model, usage["prompt_tokens"], usage["completion_tokens"])
                attempt.status = "success"
                attempt.latency_ms = latency_ms
                attempt.prompt_tokens = usage["prompt_tokens"]
                attempt.completion_tokens = usage["completion_tokens"]
                attempt.estimated_cost = cost
                attempt.completed_at = datetime.now(timezone.utc)
                record.status = "success"
                record.selected_model_id = candidate.model.id
                record.provider_id = candidate.provider.id
                record.prompt_tokens = usage["prompt_tokens"]
                record.completion_tokens = usage["completion_tokens"]
                record.total_tokens = usage["total_tokens"]
                record.estimated_cost = cost
                record.latency_ms = (time.perf_counter() - started_request) * 1000
                record.completed_at = datetime.now(timezone.utc)
                final_body = {"id": completion_id, "object": "chat.completion", "model": request.model, "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(content_parts)}, "finish_reason": "stop"}], "usage": usage, "modeldock": {"trace_id": trace_id}}
                record.metadata_json = {**(record.metadata_json or {}), **decision, "selected": {"provider": candidate.provider.name, "model": candidate.model.model_name}, **({"idempotency_response": final_body} if idempotency_key else {})}
                await session.commit()
                yield _stream_event(completion_id, request, trace_id, finish_reason="stop", usage=usage)
                yield "data: [DONE]\n\n"
                return
            except ProviderError as exc:
                if exc.retryable and exc.error_type != "provider_concurrency_limit":
                    record_provider_failure(candidate.provider, (time.perf_counter() - started) * 1000)
                final_error = exc
                attempt.status = "error"
                attempt.error_type = exc.error_type
                attempt.error_message = exc.message[:1000]
                attempt.latency_ms = (time.perf_counter() - started) * 1000
                attempt.completed_at = datetime.now(timezone.utc)
                await session.flush()
                if streamed or not exc.retryable or retry_index >= settings.max_retries_per_provider:
                    break
                await asyncio.sleep(0.05 * (2**retry_index))
        if streamed and final_error:
            break
    record.status = "error"
    record.latency_ms = (time.perf_counter() - started_request) * 1000
    record.completed_at = datetime.now(timezone.utc)
    record.metadata_json = {**(record.metadata_json or {}), **decision, "error": {"type": final_error.error_type if final_error else "provider_error", "message": final_error.message if final_error else "No provider succeeded"}}
    await session.commit()
    error_payload = {"error": {"message": final_error.message if final_error else "No provider succeeded", "type": final_error.error_type if final_error else "provider_unavailable"}, "modeldock": {"trace_id": trace_id}}
    yield f'data: {json.dumps(error_payload, separators=(",", ":"))}\n\n'
    yield "data: [DONE]\n\n"
