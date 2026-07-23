from datetime import datetime
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ModelDockRequestOptions(BaseModel):
    token_mode: Literal["inherit", "off", "safe", "caveman", "ponytail", "stacked"] = "inherit"


class ChatCompletionRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    messages: list[Message] = Field(min_length=1, max_length=200)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0, le=100_000)
    max_completion_tokens: int | None = Field(default=None, gt=0, le=100_000)
    stop: str | list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    stream: bool = False
    task_type: str | None = Field(default=None, max_length=80)
    data_classification: str | None = Field(default=None, max_length=80)
    metadata: dict[str, Any] = Field(default_factory=dict)
    modeldock: ModelDockRequestOptions = Field(default_factory=ModelDockRequestOptions)

    @model_validator(mode="after")
    def validate_token_limit(self) -> "ChatCompletionRequest":
        if self.max_tokens is not None and self.max_completion_tokens is not None:
            raise ValueError("Use max_tokens or max_completion_tokens, not both")
        return self


class TokenPolicyUpdate(BaseModel):
    safe: bool = False
    caveman: bool = False
    ponytail: bool = False


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider_type: Literal["openai", "openai_responses", "anthropic", "gemini", "groq", "ollama", "openai_compatible"]
    credentials: dict[str, Any] = Field(default_factory=dict)
    base_url: str | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=300)
    concurrency_limit: int = Field(default=8, ge=1, le=10_000)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_provider_url(self) -> "ProviderCreate":
        if self.provider_type == "openai_compatible" and not self.base_url:
            raise ValueError("base_url is required for openai_compatible providers")
        return self


class ProviderAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    credentials: dict[str, Any] = Field(min_length=1)
    priority: int = Field(default=100, ge=0, le=100_000)
    enabled: bool = True
    quota_remaining: int | None = Field(default=None, ge=0)
    quota_reset_at: datetime | None = None


class ProviderAccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credentials: dict[str, Any] | None = Field(default=None, min_length=1)
    priority: int | None = Field(default=None, ge=0, le=100_000)
    enabled: bool | None = None
    quota_remaining: int | None = Field(default=None, ge=0)
    quota_reset_at: datetime | None = None


class ProviderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credentials: dict[str, Any] | None = None
    base_url: str | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    concurrency_limit: int | None = Field(default=None, ge=1, le=10_000)
    enabled: bool | None = None


class ModelCreate(BaseModel):
    provider_id: str
    model_name: str = Field(min_length=1, max_length=160)
    display_name: str | None = None
    context_window: int = Field(default=8192, gt=0)
    capabilities: list[str] = Field(default_factory=lambda: ["chat"])
    pricing: dict[str, float] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    quality_score: float = Field(default=0.5, ge=0, le=1)
    enabled: bool = True


class ModelUpdate(BaseModel):
    model_name: str | None = Field(default=None, min_length=1, max_length=160)
    display_name: str | None = None
    context_window: int | None = Field(default=None, gt=0)
    capabilities: list[str] | None = None
    pricing: dict[str, float] | None = None
    tags: list[str] | None = None
    quality_score: float | None = Field(default=None, ge=0, le=1)
    enabled: bool | None = None


def validate_virtual_model_config(candidates: list[dict[str, Any]], strategy_config: dict[str, float]) -> None:
    for candidate in candidates:
        if not candidate.get("model_id") and not candidate.get("model"):
            raise ValueError("each candidate requires model_id or model")
        for field in ("weight", "quality_score", "reliability_score"):
            if field not in candidate:
                continue
            try:
                value = float(candidate[field])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"candidate {field} must be numeric") from exc
            if not isfinite(value) or value < 0 or (field != "weight" and value > 1):
                raise ValueError(f"candidate {field} is out of range")
    if any(not isfinite(value) or value < 0 for value in strategy_config.values()):
        raise ValueError("strategy_config weights must be finite and non-negative")
    if float(strategy_config.get("canary_percent", 0)) > 100:
        raise ValueError("canary_percent must be between 0 and 100")


class VirtualModelCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    strategy: Literal["priority", "cheapest", "fastest", "weighted_random", "weighted_score", "canary"] = "priority"
    candidates: list[dict[str, Any]] = Field(min_length=1)
    strategy_config: dict[str, float] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_config(self) -> "VirtualModelCreate":
        validate_virtual_model_config(self.candidates, self.strategy_config)
        if self.strategy == "canary" and len(self.candidates) < 2:
            raise ValueError("canary strategy requires control and variant candidates")
        return self


class VirtualModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    strategy: Literal["priority", "cheapest", "fastest", "weighted_random", "weighted_score", "canary"] | None = None
    candidates: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    strategy_config: dict[str, float] | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_config(self) -> "VirtualModelUpdate":
        validate_virtual_model_config(self.candidates or [], self.strategy_config or {})
        if self.strategy == "canary" and self.candidates is not None and len(self.candidates) < 2:
            raise ValueError("canary strategy requires control and variant candidates")
        return self


class APIKeyCreate(BaseModel):
    project_id: str
    environment_id: str | None = None
    name: str = Field(min_length=1, max_length=120)
    environment: Literal["live", "test"] = "live"
    expires_at: datetime | None = None
    rate_limit_rpm: int = Field(default=60, ge=0, le=100_000)
    token_limit_monthly: int | None = Field(default=None, gt=0)
    concurrent_limit: int = Field(default=4, ge=1, le=1_000)
    allowed_models: list[str] = Field(default_factory=list)
    allowed_ips: list[str] = Field(default_factory=list)


class BudgetCreate(BaseModel):
    scope_type: Literal["project"] = "project"
    scope_id: str
    period: Literal["monthly"] = "monthly"
    limit_amount: float = Field(gt=0)
    warning_threshold: float = Field(default=0.8, gt=0, le=1)
    action_at_limit: Literal["warn", "block"] = "block"


class BudgetUpdate(BaseModel):
    limit_amount: float | None = Field(default=None, gt=0)
    warning_threshold: float | None = Field(default=None, gt=0, le=1)
    action_at_limit: Literal["warn", "block"] | None = None


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_id: str
    model_name: str
    display_name: str | None
    context_window: int
    capabilities_json: list[str]
    pricing_json: dict[str, Any]
    tags_json: list[str]
    enabled: bool


class ReadProvider(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider_type: str
    base_url: str | None
    timeout_seconds: float
    enabled: bool
    has_credentials: bool = False


class APIKeyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: Literal["active", "revoked"] | None = None
    expires_at: datetime | None = None
    rate_limit_rpm: int | None = Field(default=None, ge=0, le=100_000)
    token_limit_monthly: int | None = Field(default=None, gt=0)
    concurrent_limit: int | None = Field(default=None, ge=1, le=1_000)
    allowed_models: list[str] | None = None
    allowed_ips: list[str] | None = None


class RoutingRuleCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    priority: int = 100
    condition: dict[str, Any] = Field(default_factory=dict)
    action: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class RoutingRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    priority: int | None = None
    condition: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    enabled: bool | None = None


class RoutingSimulation(BaseModel):
    project_id: str
    model: str
    task_type: str | None = None
    data_classification: str | None = None
    estimated_prompt_tokens: int = Field(default=1, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PromptCreate(BaseModel):
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    content: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None


class PromptVersionCreate(BaseModel):
    content: str = Field(min_length=1)
    variables: list[str] = Field(default_factory=list)
    model_configuration: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None


class PromptActivate(BaseModel):
    version: int = Field(gt=0)


class PromptRender(BaseModel):
    variables: dict[str, Any] = Field(default_factory=dict)
    version: int | None = Field(default=None, gt=0)


class EvaluationRun(BaseModel):
    evaluation_type: Literal["rule_set", "llm_judge"] = "rule_set"
    request_id: str | None = None
    output_text: str | None = None
    checks: dict[str, Any] = Field(default_factory=dict)
    judge_model_id: str | None = None
    rubric: str | None = None
    asynchronous: bool = False

    @model_validator(mode="after")
    def validate_evaluation(self) -> "EvaluationRun":
        if self.evaluation_type == "rule_set" and not self.checks:
            raise ValueError("checks is required for rule_set evaluation")
        if self.evaluation_type == "llm_judge" and (not self.judge_model_id or not self.rubric):
            raise ValueError("judge_model_id and rubric are required for llm_judge evaluation")
        return self


class AdminUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["owner", "admin", "developer", "viewer"] = "viewer"


class AdminLogin(BaseModel):
    email: str
    password: str

class AdminUserUpdate(BaseModel):
    role: Literal["owner", "admin", "developer", "viewer"] | None = None
    active: bool | None = None


class ResponsesRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    input: str | list[dict[str, Any]] = Field(min_length=1)
    instructions: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_output_tokens: int | None = Field(default=None, gt=0, le=100_000)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    modeldock: ModelDockRequestOptions = Field(default_factory=ModelDockRequestOptions)


class AnthropicMessageInput(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class AnthropicMessagesRequest(BaseModel):
    model: str = Field(min_length=1, max_length=160)
    messages: list[AnthropicMessageInput] = Field(min_length=1, max_length=200)
    max_tokens: int = Field(default=1024, gt=0, le=100_000)
    system: str | list[dict[str, Any]] | None = None
    temperature: float | None = Field(default=None, ge=0, le=1)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stop_sequences: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    modeldock: ModelDockRequestOptions = Field(default_factory=ModelDockRequestOptions)
