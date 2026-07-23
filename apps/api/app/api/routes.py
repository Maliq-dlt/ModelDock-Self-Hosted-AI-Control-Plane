import json
import re
import time
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import Integer, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.concurrency import request_slot
from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import CredentialConfigurationError, create_admin_token, create_api_key, encrypt_credentials, hash_password, require_admin, require_admin_role, require_api_key, verify_password
from app.models import APIKey, AdminUser, AuditLog, Budget, Environment, Evaluation, ModelRecord, PromptTemplate, PromptVersion, Project, Provider, RequestAttempt, RequestRecord, RoutingRule, VirtualModel
from app.providers.adapters import ProviderError, adapter_for
from app.schemas import APIKeyCreate, APIKeyUpdate, AdminLogin, AdminUserCreate, BudgetCreate, BudgetUpdate, ChatCompletionRequest, EvaluationRun, ModelCreate, ModelUpdate, PromptActivate, PromptCreate, PromptRender, PromptVersionCreate, ProjectCreate, ProviderCreate, ProviderUpdate, RoutingRuleCreate, RoutingRuleUpdate, RoutingSimulation, VirtualModelCreate, VirtualModelUpdate
from app.routing.engine import resolve_route
from app.services.gateway import BudgetExceeded, QuotaExceeded, execute_chat, prepare_stream_chat, stream_chat_events
from app.services.retention import purge_retained_data

router = APIRouter()
admin = APIRouter(prefix="/api", dependencies=[Depends(require_admin)])
auth_router = APIRouter(prefix="/api/auth")

def project_json(project: Project) -> dict[str, Any]:
    return {"id": project.id, "name": project.name, "slug": project.slug, "description": project.description, "created_at": project.created_at}

def provider_json(provider: Provider) -> dict[str, Any]:
    return {"id": provider.id, "name": provider.name, "provider_type": provider.provider_type, "base_url": provider.base_url, "timeout_seconds": provider.timeout_seconds, "enabled": provider.enabled, "has_credentials": bool(provider.encrypted_credentials), "health_status": provider.health_status, "last_health_checked_at": provider.last_health_checked_at, "last_health_latency_ms": provider.last_health_latency_ms, "created_at": provider.created_at, "updated_at": provider.updated_at}

def model_json(model: ModelRecord) -> dict[str, Any]:
    return {"id": model.id, "provider_id": model.provider_id, "model_name": model.model_name, "display_name": model.display_name, "context_window": model.context_window, "capabilities": model.capabilities_json, "pricing": model.pricing_json, "tags": model.tags_json, "enabled": model.enabled, "created_at": model.created_at, "updated_at": model.updated_at}

def virtual_model_json(model: VirtualModel) -> dict[str, Any]:
    return {"id": model.id, "project_id": model.project_id, "name": model.name, "strategy": model.strategy, "candidates": model.configuration_json.get("candidates", []), "enabled": model.enabled, "created_at": model.created_at, "updated_at": model.updated_at}

def budget_json(budget: Budget) -> dict[str, Any]:
    return {"id": budget.id, "scope_type": budget.scope_type, "scope_id": budget.scope_id, "period": budget.period, "limit_amount": budget.limit_amount, "warning_threshold": budget.warning_threshold, "action_at_limit": budget.action_at_limit, "created_at": budget.created_at, "updated_at": budget.updated_at}

async def commit_or_conflict(session: AsyncSession, message: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail=message) from exc

@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/ready")
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ready"}

@admin.get("/projects")
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [project_json(item) for item in (await session.scalars(select(Project).order_by(Project.created_at.desc()))).all()]

@admin.post("/projects", status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    slug = payload.slug or re.sub(r"[^a-z0-9]+", "-", payload.name.lower()).strip("-")
    if not slug:
        raise HTTPException(status_code=422, detail="Project slug cannot be empty")
    project = Project(id=str(uuid4()), name=payload.name, slug=slug, description=payload.description)
    session.add(project)
    environment = Environment(project_id=project.id, name="Production", type="production")
    session.add(environment)
    await commit_or_conflict(session, "Project slug already exists")
    result = project_json(project)
    result["default_environment_id"] = environment.id
    return result

@admin.get("/providers")
async def list_providers(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [provider_json(item) for item in (await session.scalars(select(Provider).order_by(Provider.created_at.desc()))).all()]

@admin.post("/providers", status_code=status.HTTP_201_CREATED)
async def create_provider(payload: ProviderCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    try:
        encrypted = encrypt_credentials(payload.credentials) if payload.credentials else None
    except CredentialConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    provider = Provider(name=payload.name, provider_type=payload.provider_type, encrypted_credentials=encrypted, base_url=payload.base_url, timeout_seconds=payload.timeout_seconds, enabled=payload.enabled)
    session.add(provider)
    await commit_or_conflict(session, "Provider name already exists")
    return provider_json(provider)

@admin.get("/providers/{provider_id}")
async def get_provider(provider_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    provider = await session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider_json(provider)

@admin.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, payload: ProviderUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    provider = await session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    values = payload.model_dump(exclude_unset=True)
    credentials = values.pop("credentials", None)
    if credentials is not None:
        try:
            provider.encrypted_credentials = encrypt_credentials(credentials) if credentials else None
        except CredentialConfigurationError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
    for key, value in values.items():
        setattr(provider, key, value)
    await commit_or_conflict(session, "Provider name already exists")
    return provider_json(provider)

@admin.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(provider_id: str, session: AsyncSession = Depends(get_session)) -> None:
    provider = await session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await session.delete(provider)
    await session.commit()

@admin.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    provider = await session.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    model = await session.scalar(select(ModelRecord).where(ModelRecord.provider_id == provider.id, ModelRecord.enabled.is_(True)))
    if not model:
        raise HTTPException(status_code=409, detail="Register an enabled model before testing provider")
    started = time.perf_counter()
    try:
        healthy = await adapter_for(provider, model).health_check()
        provider.health_status = "healthy" if healthy else "unhealthy"
        error = None
    except (ProviderError, CredentialConfigurationError) as exc:
        healthy = False
        provider.health_status = "unhealthy"
        error = str(exc)
    provider.last_health_checked_at = datetime.now(timezone.utc)
    provider.last_health_latency_ms = (time.perf_counter() - started) * 1000
    await session.commit()
    return {"healthy": healthy, "health_status": provider.health_status, "latency_ms": provider.last_health_latency_ms, **({"error": error} if error else {})}

@admin.get("/models")
async def list_models(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [model_json(item) for item in (await session.scalars(select(ModelRecord).order_by(ModelRecord.created_at.desc()))).all()]

@admin.post("/models", status_code=status.HTTP_201_CREATED)
async def create_model(payload: ModelCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Provider, payload.provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    model = ModelRecord(provider_id=payload.provider_id, model_name=payload.model_name, display_name=payload.display_name, context_window=payload.context_window, capabilities_json=payload.capabilities, pricing_json=payload.pricing, tags_json=payload.tags, enabled=payload.enabled)
    session.add(model)
    await commit_or_conflict(session, "Model already exists for provider")
    return model_json(model)

@admin.patch("/models/{model_id}")
async def update_model(model_id: str, payload: ModelUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    model = await session.get(ModelRecord, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    mapping = {"capabilities": "capabilities_json", "pricing": "pricing_json", "tags": "tags_json"}
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, mapping.get(key, key), value)
    await commit_or_conflict(session, "Model already exists for provider")
    return model_json(model)

@admin.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: str, session: AsyncSession = Depends(get_session)) -> None:
    model = await session.get(ModelRecord, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    await session.delete(model)
    await session.commit()

@admin.get("/virtual-models")
async def list_virtual_models(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [virtual_model_json(item) for item in (await session.scalars(select(VirtualModel).order_by(VirtualModel.created_at.desc()))).all()]

@admin.post("/virtual-models", status_code=status.HTTP_201_CREATED)
async def create_virtual_model(payload: VirtualModelCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    model = VirtualModel(project_id=payload.project_id, name=payload.name, strategy=payload.strategy, configuration_json={"candidates": payload.candidates}, enabled=payload.enabled)
    session.add(model)
    await commit_or_conflict(session, "Virtual model name already exists in project")
    return virtual_model_json(model)

@admin.get("/virtual-models/{virtual_model_id}")
async def get_virtual_model(virtual_model_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    model = await session.get(VirtualModel, virtual_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Virtual model not found")
    return virtual_model_json(model)

@admin.patch("/virtual-models/{virtual_model_id}")
async def update_virtual_model(virtual_model_id: str, payload: VirtualModelUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    model = await session.get(VirtualModel, virtual_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Virtual model not found")
    values = payload.model_dump(exclude_unset=True)
    candidates = values.pop("candidates", None)
    if candidates is not None:
        model.configuration_json = {**model.configuration_json, "candidates": candidates}
    for key, value in values.items():
        setattr(model, key, value)
    await commit_or_conflict(session, "Virtual model name already exists in project")
    return virtual_model_json(model)

@admin.delete("/virtual-models/{virtual_model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_virtual_model(virtual_model_id: str, session: AsyncSession = Depends(get_session)) -> None:
    model = await session.get(VirtualModel, virtual_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Virtual model not found")
    await session.delete(model)
    await session.commit()

@admin.get("/api-keys")
async def list_api_keys(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(APIKey).order_by(APIKey.created_at.desc()))).all()
    return [{"id": item.id, "project_id": item.project_id, "environment_id": item.environment_id, "name": item.name, "key_prefix": item.key_prefix, "status": item.status, "expires_at": item.expires_at, "last_used_at": item.last_used_at, "rate_limit_rpm": item.rate_limit_rpm, "token_limit_monthly": item.token_limit_monthly, "concurrent_limit": item.concurrent_limit, "allowed_models": item.allowed_models_json, "allowed_ips": item.allowed_ips_json, "created_at": item.created_at} for item in rows]

@admin.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_project_api_key(payload: APIKeyCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    environment_id = payload.environment_id
    if environment_id:
        environment = await session.get(Environment, environment_id)
        if not environment or environment.project_id != payload.project_id:
            raise HTTPException(status_code=404, detail="Environment not found for project")
    else:
        environment = await session.scalar(select(Environment).where(Environment.project_id == payload.project_id).order_by(Environment.created_at))
        if not environment:
            raise HTTPException(status_code=409, detail="Project has no environment")
        environment_id = environment.id
    try:
        raw_key, prefix, key_hash = create_api_key(payload.environment)
    except CredentialConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    api_key = APIKey(project_id=payload.project_id, environment_id=environment_id, name=payload.name, key_prefix=prefix, key_hash=key_hash, expires_at=payload.expires_at, rate_limit_rpm=payload.rate_limit_rpm, token_limit_monthly=payload.token_limit_monthly, concurrent_limit=payload.concurrent_limit, allowed_models_json=payload.allowed_models, allowed_ips_json=payload.allowed_ips)
    session.add(api_key)
    await session.commit()
    return {"id": api_key.id, "project_id": api_key.project_id, "environment_id": api_key.environment_id, "name": api_key.name, "key_prefix": api_key.key_prefix, "raw_key": raw_key, "created_at": api_key.created_at}

@admin.patch("/api-keys/{key_id}")
async def update_api_key(key_id: str, payload: APIKeyUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    api_key = await session.get(APIKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    values = payload.model_dump(exclude_unset=True)
    mapping = {"allowed_models": "allowed_models_json", "allowed_ips": "allowed_ips_json"}
    for key, value in values.items():
        setattr(api_key, mapping.get(key, key), value)
    await session.commit()
    return {"id": api_key.id, "name": api_key.name, "status": api_key.status, "rate_limit_rpm": api_key.rate_limit_rpm, "token_limit_monthly": api_key.token_limit_monthly, "concurrent_limit": api_key.concurrent_limit, "allowed_models": api_key.allowed_models_json, "allowed_ips": api_key.allowed_ips_json}

@admin.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(key_id: str, session: AsyncSession = Depends(get_session)) -> None:
    api_key = await session.get(APIKey, key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")
    api_key.status = "revoked"
    await session.commit()

@admin.post("/api-keys/{key_id}/rotate")
async def rotate_api_key(key_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    current = await session.get(APIKey, key_id)
    if not current:
        raise HTTPException(status_code=404, detail="API key not found")
    environment = "test" if current.key_prefix.startswith("md_test_") else "live"
    try:
        raw_key, prefix, key_hash = create_api_key(environment)
    except CredentialConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    current.status = "revoked"
    replacement = APIKey(project_id=current.project_id, environment_id=current.environment_id, name=current.name, key_prefix=prefix, key_hash=key_hash, expires_at=current.expires_at, rate_limit_rpm=current.rate_limit_rpm, token_limit_monthly=current.token_limit_monthly, concurrent_limit=current.concurrent_limit, allowed_models_json=current.allowed_models_json, allowed_ips_json=current.allowed_ips_json)
    session.add(replacement)
    await session.commit()
    return {"id": replacement.id, "key_prefix": replacement.key_prefix, "raw_key": raw_key, "created_at": replacement.created_at}

@admin.get("/budgets")
async def list_budgets(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    return [budget_json(item) for item in (await session.scalars(select(Budget).order_by(Budget.created_at.desc()))).all()]

@admin.post("/budgets", status_code=status.HTTP_201_CREATED)
async def create_budget(payload: BudgetCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Project, payload.scope_id):
        raise HTTPException(status_code=404, detail="Project not found")
    existing = await session.scalar(select(Budget).where(Budget.scope_type == payload.scope_type, Budget.scope_id == payload.scope_id, Budget.period == payload.period))
    if existing:
        raise HTTPException(status_code=409, detail="Budget already exists for scope and period")
    budget = Budget(**payload.model_dump())
    session.add(budget)
    await session.commit()
    return budget_json(budget)

@admin.patch("/budgets/{budget_id}")
async def update_budget(budget_id: str, payload: BudgetUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    budget = await session.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(budget, key, value)
    await session.commit()
    return budget_json(budget)

@admin.delete("/budgets/{budget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget(budget_id: str, session: AsyncSession = Depends(get_session)) -> None:
    budget = await session.get(Budget, budget_id)
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    await session.delete(budget)
    await session.commit()

@admin.get("/traces")
async def list_traces(
    limit: int = Query(default=50, ge=1, le=500),
    page: int = Query(default=1, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
    virtual_model: str | None = None,
    project_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    query = select(RequestRecord).order_by(RequestRecord.started_at.desc())
    if status_filter:
        query = query.where(RequestRecord.status == status_filter)
    if virtual_model:
        query = query.where(RequestRecord.virtual_model == virtual_model)
    if project_id:
        query = query.where(RequestRecord.project_id == project_id)
    rows = (await session.scalars(query.offset((page - 1) * limit).limit(limit))).all()
    return [{"trace_id": item.trace_id, "project_id": item.project_id, "virtual_model": item.virtual_model, "status": item.status, "prompt_tokens": item.prompt_tokens, "completion_tokens": item.completion_tokens, "total_tokens": item.total_tokens, "estimated_cost": item.estimated_cost, "latency_ms": item.latency_ms, "started_at": item.started_at, "completed_at": item.completed_at, "metadata": item.metadata_json} for item in rows]

@admin.get("/traces/{trace_id}")
async def get_trace(trace_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    request_record = await session.scalar(select(RequestRecord).where(RequestRecord.trace_id == trace_id))
    if not request_record:
        raise HTTPException(status_code=404, detail="Trace not found")
    attempts = (await session.scalars(select(RequestAttempt).where(RequestAttempt.request_id == request_record.id).order_by(RequestAttempt.attempt_number))).all()
    return {"trace_id": request_record.trace_id, "status": request_record.status, "virtual_model": request_record.virtual_model, "selected_model_id": request_record.selected_model_id, "provider_id": request_record.provider_id, "usage": {"prompt_tokens": request_record.prompt_tokens, "completion_tokens": request_record.completion_tokens, "total_tokens": request_record.total_tokens, "estimated_cost": request_record.estimated_cost}, "latency_ms": request_record.latency_ms, "started_at": request_record.started_at, "completed_at": request_record.completed_at, "metadata": request_record.metadata_json, "attempts": [{"attempt_number": item.attempt_number, "provider_id": item.provider_id, "model_id": item.model_id, "status": item.status, "error_type": item.error_type, "error_message": item.error_message, "latency_ms": item.latency_ms, "estimated_cost": item.estimated_cost, "started_at": item.started_at, "completed_at": item.completed_at} for item in attempts]}

@admin.get("/usage/summary")
async def usage_summary(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    row = (await session.execute(select(func.count(RequestRecord.id), func.coalesce(func.sum(RequestRecord.total_tokens), 0), func.coalesce(func.sum(RequestRecord.estimated_cost), 0.0), func.coalesce(func.avg(RequestRecord.latency_ms), 0.0), func.coalesce(func.sum(func.cast(RequestRecord.status == "error", Integer)), 0)).where(RequestRecord.started_at >= start))).one()
    elapsed_days = max(1, (datetime.now(timezone.utc).date() - start.date()).days + 1)
    now = datetime.now(timezone.utc)
    days_in_month = monthrange(now.year, now.month)[1]
    projected_cost = float(row[2]) / elapsed_days * days_in_month
    return {"period_start": start, "requests": int(row[0]), "total_tokens": int(row[1]), "estimated_cost": float(row[2]), "projected_monthly_cost": projected_cost, "average_latency_ms": float(row[3]), "errors": int(row[4])}

@admin.get("/usage/timeseries")
async def usage_timeseries(days: int = Query(default=30, ge=1, le=365), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    start = datetime.now(timezone.utc) - timedelta(days=days - 1)
    rows = (await session.scalars(select(RequestRecord).where(RequestRecord.started_at >= start).order_by(RequestRecord.started_at))).all()
    buckets: dict[str, dict[str, Any]] = {}
    for item in rows:
        key = item.started_at.date().isoformat()
        bucket = buckets.setdefault(key, {"date": key, "requests": 0, "tokens": 0, "estimated_cost": 0.0})
        bucket["requests"] += 1
        bucket["tokens"] += item.total_tokens
        bucket["estimated_cost"] += item.estimated_cost
    return list(buckets.values())

@admin.get("/usage/by-model")
async def usage_by_model(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(ModelRecord.model_name, func.count(RequestRecord.id), func.coalesce(func.sum(RequestRecord.total_tokens), 0), func.coalesce(func.sum(RequestRecord.estimated_cost), 0.0)).join(RequestRecord, RequestRecord.selected_model_id == ModelRecord.id).group_by(ModelRecord.model_name).order_by(func.sum(RequestRecord.estimated_cost).desc()))).all()
    return [{"model": row[0], "requests": int(row[1]), "total_tokens": int(row[2]), "estimated_cost": float(row[3])} for row in rows]

@admin.get("/usage/by-provider")
async def usage_by_provider(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Provider.name, func.count(RequestRecord.id), func.coalesce(func.sum(RequestRecord.total_tokens), 0), func.coalesce(func.sum(RequestRecord.estimated_cost), 0.0)).join(RequestRecord, RequestRecord.provider_id == Provider.id).group_by(Provider.name).order_by(func.sum(RequestRecord.estimated_cost).desc()))).all()
    return [{"provider": row[0], "requests": int(row[1]), "total_tokens": int(row[2]), "estimated_cost": float(row[3])} for row in rows]

@admin.get("/usage/by-project")
async def usage_by_project(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.execute(select(Project.id, Project.name, func.count(RequestRecord.id), func.coalesce(func.sum(RequestRecord.total_tokens), 0), func.coalesce(func.sum(RequestRecord.estimated_cost), 0.0)).join(RequestRecord, RequestRecord.project_id == Project.id).group_by(Project.id, Project.name).order_by(func.sum(RequestRecord.estimated_cost).desc()))).all()
    return [{"project_id": row[0], "project": row[1], "requests": int(row[2]), "total_tokens": int(row[3]), "estimated_cost": float(row[4])} for row in rows]

@router.get("/v1/models")
async def openai_models(api_key: APIKey = Depends(require_api_key), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    virtuals = (await session.scalars(select(VirtualModel).where(VirtualModel.project_id == api_key.project_id, VirtualModel.enabled.is_(True)))).all()
    models = (await session.scalars(select(ModelRecord).where(ModelRecord.enabled.is_(True)))).all()
    data = [{"id": item.name, "object": "model", "created": int(item.created_at.timestamp()), "owned_by": "modeldock"} for item in virtuals]
    data.extend({"id": item.model_name, "object": "model", "created": int(item.created_at.timestamp()), "owned_by": "modeldock"} for item in models)
    return {"object": "list", "data": data}

@router.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    api_key: APIKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    if payload.stream:
        try:
            trace_id, replay, record, candidates, decision, prompt_tokens = await prepare_stream_chat(session, api_key, payload, idempotency_key)
        except (BudgetExceeded, QuotaExceeded) as exc:
            error_type = "budget_exceeded" if isinstance(exc, BudgetExceeded) else "quota_exceeded"
            return JSONResponse(status_code=402 if error_type == "budget_exceeded" else 429, content={"error": {"message": str(exc), "type": error_type, "code": error_type}, "modeldock": {"trace_id": exc.trace_id}}, headers={"X-ModelDock-Trace-ID": exc.trace_id})

        async def events():
            if replay:
                message = ((replay.get("choices") or [{}])[0].get("message") or {})
                payload_chunk = {"id": replay.get("id"), "object": "chat.completion.chunk", "created": int(time.time()), "model": replay.get("model", payload.model), "choices": [{"index": 0, "delta": {"content": message.get("content") or ""}, "finish_reason": None}], "modeldock": replay.get("modeldock", {"trace_id": trace_id})}
                yield f'data: {json.dumps(payload_chunk, separators=(",", ":"))}\n\n'
                yield "data: [DONE]\n\n"
                return
            async with request_slot(api_key.id, api_key.concurrent_limit):
                async for event in stream_chat_events(session, payload, trace_id, record, candidates, decision, prompt_tokens, idempotency_key):
                    yield event

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-ModelDock-Trace-ID": trace_id})
    try:
        async with request_slot(api_key.id, api_key.concurrent_limit):
            response, trace_id = await execute_chat(session, api_key, payload, idempotency_key)
    except (BudgetExceeded, QuotaExceeded) as exc:
        error_type = "budget_exceeded" if isinstance(exc, BudgetExceeded) else "quota_exceeded"
        return JSONResponse(status_code=402 if error_type == "budget_exceeded" else 429, content={"error": {"message": str(exc), "type": error_type, "code": error_type}, "modeldock": {"trace_id": exc.trace_id}}, headers={"X-ModelDock-Trace-ID": exc.trace_id})
    except ProviderError as exc:
        body: dict[str, Any] = {"error": {"message": exc.message, "type": exc.error_type, "code": exc.error_type}}
        headers = {}
        if exc.trace_id:
            body["modeldock"] = {"trace_id": exc.trace_id}
            headers["X-ModelDock-Trace-ID"] = exc.trace_id
        return JSONResponse(status_code=exc.status_code if 400 <= exc.status_code < 600 else 502, content=body, headers=headers)
    return JSONResponse(content=response, headers={"X-ModelDock-Trace-ID": trace_id})

@admin.get("/routing-rules")
async def list_routing_rules(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    query = select(RoutingRule).order_by(RoutingRule.priority, RoutingRule.created_at)
    if project_id:
        query = query.where(RoutingRule.project_id == project_id)
    rows = (await session.scalars(query)).all()
    return [{"id": item.id, "project_id": item.project_id, "name": item.name, "priority": item.priority, "condition": item.condition_json, "action": item.action_json, "enabled": item.enabled} for item in rows]

@admin.post("/routing-rules", status_code=status.HTTP_201_CREATED)
async def create_routing_rule(payload: RoutingRuleCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    rule = RoutingRule(project_id=payload.project_id, name=payload.name, priority=payload.priority, condition_json=payload.condition, action_json=payload.action, enabled=payload.enabled)
    session.add(rule)
    await session.commit()
    return {"id": rule.id, "project_id": rule.project_id, "name": rule.name, "priority": rule.priority, "condition": rule.condition_json, "action": rule.action_json, "enabled": rule.enabled}

@admin.patch("/routing-rules/{rule_id}")
async def update_routing_rule(rule_id: str, payload: RoutingRuleUpdate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    rule = await session.get(RoutingRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    values = payload.model_dump(exclude_unset=True)
    mapping = {"condition": "condition_json", "action": "action_json"}
    for key, value in values.items():
        setattr(rule, mapping.get(key, key), value)
    await session.commit()
    return {"id": rule.id, "project_id": rule.project_id, "name": rule.name, "priority": rule.priority, "condition": rule.condition_json, "action": rule.action_json, "enabled": rule.enabled}

@admin.delete("/routing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing_rule(rule_id: str, session: AsyncSession = Depends(get_session)) -> None:
    rule = await session.get(RoutingRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    await session.delete(rule)
    await session.commit()

@admin.post("/routing-rules/simulate")
async def simulate_routing(payload: RoutingSimulation, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    candidates, decision = await resolve_route(session, payload.project_id, payload.model, {"task_type": payload.task_type, "data_classification": payload.data_classification, "estimated_prompt_tokens": payload.estimated_prompt_tokens, "metadata": payload.metadata})
    return {"decision": decision, "candidates": [{"provider": item.provider.name, "model": item.model.model_name, "model_id": item.model.id, "reason": item.reason} for item in candidates]}

@admin.get("/prompts")
async def list_prompts(project_id: str | None = None, session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    query = select(PromptTemplate).order_by(PromptTemplate.created_at.desc())
    if project_id:
        query = query.where(PromptTemplate.project_id == project_id)
    rows = (await session.scalars(query)).all()
    return [{"id": item.id, "project_id": item.project_id, "name": item.name, "description": item.description, "active_version": item.active_version, "created_at": item.created_at} for item in rows]

@admin.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(payload: PromptCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(Project, payload.project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    prompt = PromptTemplate(project_id=payload.project_id, name=payload.name, description=payload.description, active_version=1)
    session.add(prompt)
    await session.flush()
    session.add(PromptVersion(prompt_template_id=prompt.id, version=1, content=payload.content, variables_json=payload.variables, model_configuration_json=payload.model_configuration, created_by=payload.created_by))
    await session.commit()
    return {"id": prompt.id, "project_id": prompt.project_id, "name": prompt.name, "active_version": prompt.active_version}

@admin.get("/prompts/{prompt_id}/versions")
async def list_prompt_versions(prompt_id: str, session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    if not await session.get(PromptTemplate, prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    rows = (await session.scalars(select(PromptVersion).where(PromptVersion.prompt_template_id == prompt_id).order_by(PromptVersion.version))).all()
    return [{"id": item.id, "version": item.version, "content": item.content, "variables": item.variables_json, "model_configuration": item.model_configuration_json, "created_by": item.created_by, "created_at": item.created_at} for item in rows]

@admin.post("/prompts/{prompt_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_prompt_version(prompt_id: str, payload: PromptVersionCreate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    if not await session.get(PromptTemplate, prompt_id):
        raise HTTPException(status_code=404, detail="Prompt not found")
    latest = await session.scalar(select(func.max(PromptVersion.version)).where(PromptVersion.prompt_template_id == prompt_id))
    version = int(latest or 0) + 1
    item = PromptVersion(prompt_template_id=prompt_id, version=version, content=payload.content, variables_json=payload.variables, model_configuration_json=payload.model_configuration, created_by=payload.created_by)
    session.add(item)
    await session.commit()
    return {"id": item.id, "version": item.version, "content": item.content, "variables": item.variables_json, "model_configuration": item.model_configuration_json}

@admin.post("/prompts/{prompt_id}/activate")
async def activate_prompt(prompt_id: str, payload: PromptActivate, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    prompt = await session.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    version = await session.scalar(select(PromptVersion).where(PromptVersion.prompt_template_id == prompt_id, PromptVersion.version == payload.version))
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    prompt.active_version = version.version
    await session.commit()
    return {"id": prompt.id, "active_version": prompt.active_version}

@admin.post("/prompts/{prompt_id}/render")
async def render_prompt(prompt_id: str, payload: PromptRender, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    prompt = await session.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")
    version_number = payload.version or prompt.active_version
    version = await session.scalar(select(PromptVersion).where(PromptVersion.prompt_template_id == prompt_id, PromptVersion.version == version_number))
    if not version:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    missing = [name for name in version.variables_json if name not in payload.variables]
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Missing prompt variables", "variables": missing})
    content = re.sub(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}", lambda match: str(payload.variables.get(match.group(1), match.group(0))), version.content)
    return {"prompt_id": prompt_id, "version": version.version, "content": content, "model_configuration": version.model_configuration_json}

@admin.get("/evaluations")
async def list_evaluations(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(Evaluation).order_by(Evaluation.created_at.desc()))).all()
    return [{"id": item.id, "request_id": item.request_id, "evaluation_type": item.evaluation_type, "score": item.score, "result": item.result_json, "created_at": item.created_at} for item in rows]

@admin.post("/evaluations/run", status_code=status.HTTP_201_CREATED)
async def run_evaluation(payload: EvaluationRun, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    request_record = await session.get(RequestRecord, payload.request_id) if payload.request_id else None
    if payload.request_id and not request_record:
        raise HTTPException(status_code=404, detail="Request not found")
    output = payload.output_text
    if output is None and request_record:
        output = ((request_record.metadata_json or {}).get("response") or {}).get("content")
    output = output or ""
    passed = 0
    total = 0
    failures = []
    for check, expected in payload.checks.items():
        total += 1
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
        if ok:
            passed += 1
        else:
            failures.append(check)
    score = passed / total if total else 0.0
    evaluation = Evaluation(request_id=payload.request_id, evaluation_type="rule_set", score=score, result_json={"passed": passed, "total": total, "failures": failures, "checks": payload.checks})
    session.add(evaluation)
    await session.commit()
    return {"id": evaluation.id, "request_id": evaluation.request_id, "evaluation_type": evaluation.evaluation_type, "score": evaluation.score, "result": evaluation.result_json}

@admin.get("/evaluations/{evaluation_id}")
async def get_evaluation(evaluation_id: str, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    item = await session.get(Evaluation, evaluation_id)
    if not item:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    return {"id": item.id, "request_id": item.request_id, "evaluation_type": item.evaluation_type, "score": item.score, "result": item.result_json, "created_at": item.created_at}

@admin.get("/audit-logs")
async def list_audit_logs(limit: int = Query(default=100, ge=1, le=500), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))).all()
    return [{"id": item.id, "actor": item.actor, "action": item.action, "resource_type": item.resource_type, "resource_id": item.resource_id, "metadata": item.metadata_json, "created_at": item.created_at} for item in rows]

@admin.post("/retention/run")
async def run_retention(retention_days: int | None = Query(default=None, ge=1, le=3650), session: AsyncSession = Depends(get_session)) -> dict[str, int]:
    return await purge_retained_data(session, retention_days or get_settings().request_retention_days)

@auth_router.post("/login")
async def admin_login(payload: AdminLogin, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    user = await session.scalar(select(AdminUser).where(AdminUser.email == payload.email.lower(), AdminUser.active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_admin_token(user), "token_type": "bearer", "role": user.role, "expires_in": 8 * 60 * 60}

@auth_router.get("/users")
async def list_admin_users(_: AdminUser | None = Depends(require_admin_role("owner", "admin")), session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    rows = (await session.scalars(select(AdminUser).order_by(AdminUser.created_at))).all()
    return [{"id": item.id, "email": item.email, "role": item.role, "active": item.active, "created_at": item.created_at} for item in rows]

@auth_router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_admin_user(payload: AdminUserCreate, _: AdminUser | None = Depends(require_admin_role("owner", "admin")), session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    user = AdminUser(email=payload.email.lower(), password_hash=hash_password(payload.password), role=payload.role)
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Email already exists") from exc
    return {"id": user.id, "email": user.email, "role": user.role, "active": user.active}

router.include_router(auth_router)
router.include_router(admin)
