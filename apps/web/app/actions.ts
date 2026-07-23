"use server";

import { revalidatePath } from "next/cache";
import { adminMutate } from "../lib/api";

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function values(form: FormData, key: string): string[] {
  return form.getAll(key).flatMap((value) => String(value).split(",")).map((value) => value.trim()).filter(Boolean);
}

function checked(form: FormData, key: string): boolean {
  return form.get(key) === "on";
}

export async function createProject(form: FormData) {
  await adminMutate("/api/projects", "POST", {
    name: text(form, "name"),
    slug: text(form, "slug") || undefined,
    description: text(form, "description") || undefined,
  });
  revalidatePath("/");
  revalidatePath("/manage");
  revalidatePath("/settings");
}

export async function createProvider(form: FormData) {
  const apiKey = text(form, "api_key");
  await adminMutate("/api/providers", "POST", {
    name: text(form, "name"),
    provider_type: text(form, "provider_type"),
    base_url: text(form, "base_url") || undefined,
    credentials: apiKey ? { api_key: apiKey } : {},
  });
  revalidatePath("/");
  revalidatePath("/manage");
  revalidatePath("/providers");
  revalidatePath("/settings");
}

export async function createModel(form: FormData) {
  const inputCost = Number(text(form, "input_cost_per_million") || 0);
  const outputCost = Number(text(form, "output_cost_per_million") || 0);
  const pricing = inputCost || outputCost ? { input_cost_per_million: inputCost, output_cost_per_million: outputCost } : {};
  await adminMutate("/api/models", "POST", {
    provider_id: text(form, "provider_id"),
    model_name: text(form, "model_name"),
    display_name: text(form, "display_name") || undefined,
    context_window: Number(text(form, "context_window") || 8192),
    capabilities: values(form, "capabilities").length ? values(form, "capabilities") : ["chat"],
    tags: values(form, "tags"),
    pricing,
  });
  revalidatePath("/");
  revalidatePath("/manage");
  revalidatePath("/models");
  revalidatePath("/routing");
}

export async function createVirtualModel(form: FormData) {
  const strategy = text(form, "strategy");
  await adminMutate("/api/virtual-models", "POST", {
    project_id: text(form, "project_id"),
    name: text(form, "name"),
    strategy,
    candidates: values(form, "candidates").map((modelId) => ({ model_id: modelId })),
    strategy_config: strategy === "canary" ? { canary_percent: Number(text(form, "canary_percent") || 5) } : {},
  });
  revalidatePath("/");
  revalidatePath("/manage");
  revalidatePath("/routing");
}

export type ApiKeyState = { rawKey: string; error: string };

export async function createApiKey(_: ApiKeyState, form: FormData): Promise<ApiKeyState> {
  try {
    const response = await adminMutate<{ raw_key: string }>("/api/api-keys", "POST", {
      project_id: text(form, "project_id"),
      name: text(form, "name"),
      environment: text(form, "environment") || "live",
      rate_limit_rpm: Number(text(form, "rate_limit_rpm") || 60),
      token_limit_monthly: text(form, "token_limit_monthly") ? Number(text(form, "token_limit_monthly")) : undefined,
      concurrent_limit: Number(text(form, "concurrent_limit") || 4),
    });
    revalidatePath("/");
    revalidatePath("/keys");
    return { rawKey: response.raw_key, error: "" };
  } catch (error) {
    return { rawKey: "", error: error instanceof Error ? error.message : "API key could not be created." };
  }
}

export async function createBudget(form: FormData) {
  await adminMutate("/api/budgets", "POST", {
    scope_id: text(form, "scope_id"),
    limit_amount: Number(text(form, "limit_amount")),
    warning_threshold: Number(text(form, "warning_threshold") || 0.8),
    action_at_limit: text(form, "action_at_limit"),
  });
  revalidatePath("/manage");
  revalidatePath("/budgets");
}

export async function testProvider(form: FormData) {
  await adminMutate(`/api/providers/${text(form, "provider_id")}/test`, "POST", {});
  revalidatePath("/");
  revalidatePath("/providers");
  revalidatePath("/settings");
}

export async function updateTokenPolicy(form: FormData) {
  const projectId = text(form, "project_id");
  if (!projectId) return;
  await adminMutate(`/api/projects/${projectId}/token-policy`, "PATCH", {
    safe: checked(form, "safe"),
    caveman: checked(form, "caveman"),
    ponytail: checked(form, "ponytail"),
  });
  revalidatePath("/");
  revalidatePath("/token-saver");
}
