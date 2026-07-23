# Roadmap

## Stage 1 - Token Efficiency and Project Hygiene

Status: completed

- TokenPress safe preprocessing.
- Caveman output guidance.
- Ponytail smallest-sufficient-code guidance.
- Trace token-efficiency stats.
- CLI offline preprocessing.
- CI, issue forms, dependency updates, governance docs.

## Stage 2 - Competitive Gateway Core

Status: completed

- Anthropic Messages and OpenAI Responses compatibility.
- Provider account pools.
- Quota-reset-aware routing.
- Model catalog sync.
- Provider adapter SDK.

## Stage 3 - Quality Loop

Status: in progress

- Deterministic canary routing and lane receipts.
- Route replay and explainability without provider calls.
- Project-inherited TokenPress policy and usage consumption telemetry.
- Orbital operations dashboard with topology, request ledger, and policy controls.
- Shadow evaluation.
- Tool-call success routing.
- Cost/quality optimization.

## Stage 4 - Agent Control Plane

- MCP server with scoped read/write tools.
- A2A gateway.
- Approval policy for mutations.
- Agent-level budget, trace, and data policy.

## Stage 5 - Enterprise Runtime

- OIDC/SSO and SCIM.
- KMS/Vault/External Secrets.
- Kubernetes Operator.
- PostgreSQL/Redis HA.
- Multi-region routing and disaster recovery.

## Non-goals

- No MITM subscription interception.
- No browser-cookie scraping.
- No lossy output truncation marketed as token optimization.
- No provider-count race without compatibility and quality tests.
