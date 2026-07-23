import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Evaluation, ModelRecord, Provider, RequestRecord
from app.providers.adapters import adapter_for
from app.schemas import ChatCompletionRequest

def _output_text(payload: dict[str, Any], request_record: RequestRecord | None) -> str:
    if payload.get("output_text") is not None:
        return str(payload["output_text"])
    if request_record:
        return str(((request_record.metadata_json or {}).get("response") or {}).get("content") or "")
    return ""

def _rule_result(output: str, checks: dict[str, Any], request_record: RequestRecord | None) -> tuple[float, dict[str, Any]]:
    passed = 0
    failures = []
    for check, expected in checks.items():
        ok = True
        if check == "contains":
            values = expected if isinstance(expected, list) else [expected]
            ok = all(str(value) in output for value in values)
        elif check == "regex":
            ok = re.search(str(expected), output) is not None
        elif check == "exact_match":
            ok = output == str(expected)
        elif check == "min_length":
            ok = len(output) >= int(expected)
        elif check == "max_latency_ms":
            ok = bool(request_record and request_record.latency_ms is not None and request_record.latency_ms <= float(expected))
        elif check == "max_cost_usd":
            ok = bool(request_record and request_record.estimated_cost <= float(expected))
        else:
            ok = False
        if ok:
            passed += 1
        else:
            failures.append(check)
    total = len(checks)
    return (passed / total if total else 0.0), {"passed": passed, "total": total, "failures": failures, "checks": checks}

async def evaluate_payload(session: AsyncSession, payload: dict[str, Any]) -> tuple[str, float | None, dict[str, Any]]:
    request_record = await session.get(RequestRecord, payload["request_id"]) if payload.get("request_id") else None
    if payload.get("request_id") and not request_record:
        raise ValueError("Request not found")
    output = _output_text(payload, request_record)
    evaluation_type = payload.get("evaluation_type", "rule_set")
    if evaluation_type == "rule_set":
        score, result = _rule_result(output, payload.get("checks") or {}, request_record)
        return evaluation_type, score, result
    model = await session.get(ModelRecord, payload.get("judge_model_id"))
    if not model:
        raise ValueError("Judge model not found")
    provider = await session.get(Provider, model.provider_id)
    if not provider or not provider.enabled:
        raise ValueError("Judge provider unavailable")
    request = ChatCompletionRequest(
        model=model.model_name,
        messages=[
            {"role": "system", "content": "Evaluate output. Return JSON only: a score from 0 to 1 and a reason."},
            {"role": "user", "content": f"Rubric:\n{payload.get('rubric', '')}\n\nOutput:\n{output}"},
        ],
        temperature=0,
        max_completion_tokens=300,
    )
    response = await adapter_for(provider, model).chat(request)
    raw = response.content.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"score": 0.0, "reason": raw, "raw": raw}
    score = min(1.0, max(0.0, float(parsed.get("score", 0.0))))
    return evaluation_type, score, {"score": score, "reason": str(parsed.get("reason", "")), "raw": raw, "rubric": payload.get("rubric")}

async def process_next_evaluation(session: AsyncSession) -> Evaluation | None:
    job = await session.scalar(
        select(Evaluation)
        .where(Evaluation.status == "queued")
        .order_by(Evaluation.created_at)
        .with_for_update(skip_locked=True)
    )
    if not job:
        return None
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await session.commit()
    try:
        evaluation_type, score, result = await evaluate_payload(session, job.payload_json)
        job.evaluation_type = evaluation_type
        job.score = score
        job.result_json = result
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = None
    except Exception as exc:
        job.status = "error"
        job.error_message = str(exc)[:1000]
        job.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return job