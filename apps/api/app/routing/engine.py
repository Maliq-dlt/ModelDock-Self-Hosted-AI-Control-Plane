from dataclasses import dataclass
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


async def matching_rule(
    session: AsyncSession,
    project_id: str,
    context: dict[str, Any],
) -> RoutingRule | None:
    rules = (
        await session.scalars(
            select(RoutingRule)
            .where(RoutingRule.project_id == project_id, RoutingRule.enabled.is_(True))
            .order_by(RoutingRule.priority, RoutingRule.created_at)
        )
    ).all()
    return next((rule for rule in rules if rule_matches(rule.condition_json, context)), None)


async def _resolve_candidate(session: AsyncSession, candidate: Any) -> RouteCandidate | None:
    reference = candidate.get("model_id") if isinstance(candidate, dict) else candidate
    if not reference:
        reference = candidate.get("model") if isinstance(candidate, dict) else None
    if not reference:
        return None
    model = None
    provider = None
    if isinstance(reference, str) and "/" in reference:
        provider_name, model_name = reference.split("/", 1)
        provider = await session.scalar(select(Provider).where(Provider.name == provider_name))
        if provider:
            model = await session.scalar(
                select(ModelRecord).where(
                    ModelRecord.provider_id == provider.id,
                    ModelRecord.model_name == model_name,
                )
            )
    else:
        model = await session.get(ModelRecord, str(reference))
        if model:
            provider = await session.get(Provider, model.provider_id)
    if not model or not provider or not model.enabled or not provider.enabled:
        return None
    return RouteCandidate(model=model, provider=provider, reason="priority candidate")


def _filter_requirements(
    candidates: list[RouteCandidate],
    requirements: dict[str, Any],
) -> tuple[list[RouteCandidate], list[dict[str, Any]]]:
    accepted = []
    rejected = []
    minimum_context = int(requirements.get("minimum_context_window", 0) or 0)
    capabilities = set(requirements.get("capabilities", []))
    tags = set(requirements.get("tags", []))
    for candidate in candidates:
        reasons = []
        if candidate.model.context_window < minimum_context:
            reasons.append("context window below requirement")
        if not capabilities.issubset(set(candidate.model.capabilities_json or [])):
            reasons.append("required capability unavailable")
        if not tags.issubset(set(candidate.model.tags_json or [])):
            reasons.append("required tag unavailable")
        if reasons:
            rejected.append(
                {
                    "model": candidate.model.model_name,
                    "provider": candidate.provider.name,
                    "reason": ", ".join(reasons),
                }
            )
        else:
            accepted.append(candidate)
    return accepted, rejected


async def resolve_route(
    session: AsyncSession,
    project_id: str,
    requested_model: str,
    context: dict[str, Any] | None = None,
) -> tuple[list[RouteCandidate], dict[str, Any]]:
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
        rule_decision = {
            "id": selected_rule.id,
            "name": selected_rule.name,
            "priority": selected_rule.priority,
            "action": action,
        }

    virtual = await session.scalar(
        select(VirtualModel).where(
            VirtualModel.project_id == project_id,
            VirtualModel.name == requested_model,
            VirtualModel.enabled.is_(True),
        )
    )
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
        if virtual.strategy == "cheapest":
            candidates.sort(
                key=lambda item: float(
                    (item.model.pricing_json or {}).get("input_cost_per_million", 0)
                )
                + float((item.model.pricing_json or {}).get("output_cost_per_million", 0))
            )
            reason = "cheapest strategy"
        else:
            reason = "priority strategy"
        if not candidates:
            raise HTTPException(
                status_code=503,
                detail={"message": "No enabled route candidates", "rejected_candidates": rejected},
            )
        return candidates, {
            "virtual_model": requested_model,
            "strategy": virtual.strategy,
            "reason": reason,
            "routing_rule": rule_decision,
            "rejected_candidates": rejected,
        }

    direct = await _resolve_candidate(session, requested_model)
    if not direct and "/" not in requested_model:
        direct_models = (
            await session.scalars(
                select(ModelRecord).where(
                    ModelRecord.model_name == requested_model,
                    ModelRecord.enabled.is_(True),
                )
            )
        ).all()
        if len(direct_models) > 1:
            raise HTTPException(
                status_code=409,
                detail="Model name is ambiguous; use provider/model",
            )
        if direct_models:
            model = direct_models[0]
            provider = await session.get(Provider, model.provider_id)
            if provider and provider.enabled:
                direct = RouteCandidate(model=model, provider=provider, reason="direct model")
    if not direct:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown model or virtual model: {requested_model}",
        )
    candidates, requirement_rejections = _filter_requirements([direct], requirements)
    rejected.extend(requirement_rejections)
    if not candidates:
        raise HTTPException(
            status_code=503,
            detail={"message": "Direct model violates routing requirement", "rejected_candidates": rejected},
        )
    return candidates, {
        "virtual_model": requested_model,
        "strategy": "static",
        "reason": direct.reason,
        "routing_rule": rule_decision,
        "rejected_candidates": rejected,
    }
