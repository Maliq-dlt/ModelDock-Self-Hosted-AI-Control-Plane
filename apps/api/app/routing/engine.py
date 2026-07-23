import hashlib
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModelRecord, Provider, RoutingRule, VirtualModel

@dataclass
class RouteCandidate:
    model: ModelRecord
    provider: Provider
    reason: str
    weight: float = 1.0
    quality_score: float = 0.5
    reliability_score: float = 1.0

def _compare(actual: Any, expected: Any) -> bool:
    if not isinstance(expected, dict):
        return actual == expected
    if "less_than" in expected and not (actual is not None and actual < expected["less_than"]):
        return False
    if "greater_than" in expected and not (actual is not None and actual > expected["greater_than"]):
        return False
    if "in" in expected and actual not in expected["in"]:
        return False
    if "contains" in expected:
        values = actual if isinstance(actual, list) else [actual]
        required = expected["contains"] if isinstance(expected["contains"], list) else [expected["contains"]]
        if not all(value in values for value in required):
            return False
    return True

def rule_matches(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    merged = {**context.get("metadata", {}), **context}
    return all(_compare(merged.get(key), expected) for key, expected in condition.items())

async def matching_rule(session: AsyncSession, project_id: str, context: dict[str, Any]) -> RoutingRule | None:
    rules = (
        await session.scalars(
            select(RoutingRule)
            .where(RoutingRule.project_id == project_id, RoutingRule.enabled.is_(True))
            .order_by(RoutingRule.priority, RoutingRule.created_at)
        )
    ).all()
    return next((rule for rule in rules if rule_matches(rule.condition_json, context)), None)

def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value

def _circuit_open(provider: Provider) -> bool:
    until = _as_utc(provider.circuit_open_until)
    return until is not None and until > datetime.now(timezone.utc)

async def _resolve_candidate(session: AsyncSession, candidate: Any) -> RouteCandidate | None:
    config = candidate if isinstance(candidate, dict) else {}
    reference = (config.get("model_id") or config.get("model")) if isinstance(candidate, dict) else candidate
    if not reference:
        return None
    model = None
    provider = None
    if isinstance(reference, str) and "/" in reference:
        provider_name, model_name = reference.split("/", 1)
        provider = await session.scalar(select(Provider).where(Provider.name == provider_name))
        if provider:
            model = await session.scalar(select(ModelRecord).where(ModelRecord.provider_id == provider.id, ModelRecord.model_name == model_name))
    else:
        model = await session.get(ModelRecord, str(reference))
        if model:
            provider = await session.get(Provider, model.provider_id)
    if not model or not provider or not model.enabled or not provider.enabled:
        return None
    return RouteCandidate(
        model=model,
        provider=provider,
        reason="priority candidate",
        weight=max(0.0, float(config.get("weight", 1.0))),
        quality_score=min(1.0, max(0.0, float(config.get("quality_score", model.quality_score)))),
        reliability_score=min(1.0, max(0.0, float(config.get("reliability_score", provider.reliability_score)))),
    )

def _filter_requirements(candidates: list[RouteCandidate], requirements: dict[str, Any]) -> tuple[list[RouteCandidate], list[dict[str, Any]]]:
    accepted = []
    rejected = []
    minimum_context = int(requirements.get("minimum_context_window", 0) or 0)
    capabilities = set(requirements.get("capabilities", []))
    tags = set(requirements.get("tags", []))
    for candidate in candidates:
        reasons = []
        if _circuit_open(candidate.provider):
            reasons.append("provider circuit breaker open")
        if candidate.model.context_window < minimum_context:
            reasons.append("context window below requirement")
        if not capabilities.issubset(set(candidate.model.capabilities_json or [])):
            reasons.append("required capability unavailable")
        if not tags.issubset(set(candidate.model.tags_json or [])):
            reasons.append("required tag unavailable")
        if reasons:
            rejected.append({"model": candidate.model.model_name, "provider": candidate.provider.name, "reason": ", ".join(reasons)})
        else:
            accepted.append(candidate)
    return accepted, rejected

def _cost(candidate: RouteCandidate) -> float:
    pricing = candidate.model.pricing_json or {}
    return float(pricing.get("input_cost_per_million", 0)) + float(pricing.get("output_cost_per_million", 0))

def _latency(candidate: RouteCandidate) -> float:
    return float(candidate.provider.last_health_latency_ms or 1_000_000)

def _normalise(value: float, values: list[float], higher_is_better: bool) -> float:
    low, high = min(values), max(values)
    if high == low:
        return 1.0
    score = (value - low) / (high - low)
    return score if higher_is_better else 1.0 - score

def _weighted_order(candidates: list[RouteCandidate]) -> list[RouteCandidate]:
    remaining = list(candidates)
    ordered = []
    while remaining:
        total = sum(item.weight for item in remaining)
        if total <= 0:
            ordered.extend(remaining)
            break
        target = random.random() * total
        for index, item in enumerate(remaining):
            target -= item.weight
            if target <= 0:
                ordered.append(item)
                remaining.pop(index)
                break
    return ordered

def _order_candidates(strategy: str, candidates: list[RouteCandidate], config: dict[str, float], context: dict[str, Any]) -> tuple[list[RouteCandidate], dict[str, Any]]:
    if strategy == "cheapest":
        candidates.sort(key=_cost)
        return candidates, {"reason": "cheapest strategy"}
    if strategy == "fastest":
        candidates.sort(key=_latency)
        return candidates, {"reason": "fastest strategy"}
    if strategy == "weighted_random":
        return _weighted_order(candidates), {"reason": "weighted random strategy"}
    if strategy == "canary":
        percent = min(100.0, max(0.0, float(config.get("canary_percent", 5.0))))
        routing_key = str(context.get("routing_key") or context.get("metadata", {}).get("routing_key") or "modeldock-default")
        digest = hashlib.sha256(routing_key.encode()).hexdigest()
        bucket = int(digest[:8], 16) % 10_000 / 100
        variant = bucket < percent and len(candidates) > 1
        ordered = [candidates[1], candidates[0], *candidates[2:]] if variant else candidates
        return ordered, {
            "reason": "deterministic canary strategy",
            "canary_percent": percent,
            "canary_bucket": bucket,
            "canary_lane": "variant" if variant else "control",
            "routing_key_hash": digest[:12],
        }
    if strategy == "weighted_score":
        costs = [_cost(item) for item in candidates]
        latencies = [_latency(item) for item in candidates]
        qualities = [item.quality_score for item in candidates]
        reliabilities = [item.reliability_score for item in candidates]
        quality_weight = float(config.get("quality_weight", 1.0))
        cost_weight = float(config.get("cost_weight", 0.25))
        latency_weight = float(config.get("latency_weight", 0.25))
        reliability_weight = float(config.get("reliability_weight", 0.5))
        scored = []
        for item, cost, latency, quality, reliability in zip(candidates, costs, latencies, qualities, reliabilities):
            score = (
                quality_weight * _normalise(quality, qualities, True)
                - cost_weight * _normalise(cost, costs, True)
                - latency_weight * _normalise(latency, latencies, True)
                + reliability_weight * _normalise(reliability, reliabilities, True)
            )
            scored.append((item, round(score, 6)))
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [item for item, _ in scored], {
            "reason": "weighted score strategy",
            "candidate_scores": [
                {"provider": item.provider.name, "model": item.model.model_name, "score": score}
                for item, score in scored
            ],
        }
    return candidates, {"reason": "priority strategy"}

async def resolve_route(session: AsyncSession, project_id: str, requested_model: str, context: dict[str, Any] | None = None) -> tuple[list[RouteCandidate], dict[str, Any]]:
    context = context or {}
    selected_rule = await matching_rule(session, project_id, context)
    rule_decision = None
    requirements: dict[str, Any] = {}
    if selected_rule:
        action = selected_rule.action_json or {}
        if action.get("deny"):
            raise HTTPException(status_code=403, detail=action.get("message", "Routing policy denied request"))
        requested_model = action.get("route_to", requested_model)
        requirements = action.get("require", {})
        rule_decision = {"id": selected_rule.id, "name": selected_rule.name, "priority": selected_rule.priority, "action": action}

    virtual = await session.scalar(select(VirtualModel).where(VirtualModel.project_id == project_id, VirtualModel.name == requested_model, VirtualModel.enabled.is_(True)))
    rejected: list[dict[str, Any]] = []
    if virtual:
        candidates = []
        for item in virtual.configuration_json.get("candidates", []):
            resolved = await _resolve_candidate(session, item)
            if resolved:
                candidates.append(resolved)
            else:
                rejected.append({"candidate": item, "reason": "disabled or missing provider/model"})
        candidates, requirement_rejections = _filter_requirements(candidates, requirements)
        rejected.extend(requirement_rejections)
        if not candidates:
            raise HTTPException(status_code=503, detail={"message": "No enabled route candidates", "rejected_candidates": rejected})
        ordered, order_decision = _order_candidates(virtual.strategy, candidates, virtual.configuration_json.get("strategy_config", {}), context)
        return ordered, {"virtual_model": requested_model, "strategy": virtual.strategy, **order_decision, "routing_rule": rule_decision, "rejected_candidates": rejected}

    direct = await _resolve_candidate(session, requested_model)
    if not direct and "/" not in requested_model:
        direct_models = (await session.scalars(select(ModelRecord).where(ModelRecord.model_name == requested_model, ModelRecord.enabled.is_(True)))).all()
        if len(direct_models) > 1:
            raise HTTPException(status_code=409, detail="Model name is ambiguous; use provider/model")
        if direct_models:
            model = direct_models[0]
            provider = await session.get(Provider, model.provider_id)
            if provider and provider.enabled:
                direct = RouteCandidate(model=model, provider=provider, reason="direct model", quality_score=model.quality_score, reliability_score=provider.reliability_score)
    if not direct:
        raise HTTPException(status_code=404, detail=f"Unknown model or virtual model: {requested_model}")
    candidates, requirement_rejections = _filter_requirements([direct], requirements)
    rejected.extend(requirement_rejections)
    if not candidates:
        raise HTTPException(status_code=503, detail={"message": "Direct model violates routing requirement", "rejected_candidates": rejected})
    return candidates, {"virtual_model": requested_model, "strategy": "static", "reason": direct.reason, "routing_rule": rule_decision, "rejected_candidates": rejected}