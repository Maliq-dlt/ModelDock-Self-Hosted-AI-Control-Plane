"use server";

import { revalidatePath } from "next/cache";
import { adminMutate } from "../lib/api";

function text(form: FormData, key: string): string {
  return String(form.get(key) ?? "").trim();
}

function jsonObject(form: FormData, key: string): Record<string, unknown> {
  const value = text(form, key);
  return value ? JSON.parse(value) as Record<string, unknown> : {};
}

export async function createProject(form: FormData) {
  await adminMutate("/api/projects", "POST", { name: text(form, "name"), slug: text(form, "slug") || undefined, description: text(form, "description") || undefined });
  revalidatePath("/manage");
}

export async function createProvider(form: FormData) {
  await adminMutate("/api/providers", "POST", { name: text(form, "name"), provider_type: text(form, "provider_type"), base_url: text(form, "base_url") || undefined, credentials: jsonObject(form, "credentials") });
  revalidatePath("/manage");
  revalidatePath("/providers");
}

export async function createModel(form: FormData) {
  await adminMutate("/api/models", "POST", { provider_id: text(form, "provider_id"), model_name: text(form, "model_name"), display_name: text(form, "display_name") || undefined, context_window: Number(text(form, "context_window") || 8192), capabilities: text(form, "capabilities").split(",").map(value => value.trim()).filter(Boolean), tags: text(form, "tags").split(",").map(value => value.trim()).filter(Boolean), pricing: jsonObject(form, "pricing") });
  revalidatePath("/manage");
  revalidatePath("/models");
}

export async function createVirtualModel(form: FormData) {
  await adminMutate("/api/virtual-models", "POST", { project_id: text(form, "project_id"), name: text(form, "name"), strategy: text(form, "strategy"), candidates: text(form, "candidates").split(",").map(value => ({ model_id: value.trim() })).filter(value => value.model_id) });
  revalidatePath("/manage");
}

export async function createApiKey(form: FormData) {
  await adminMutate("/api/api-keys", "POST", { project_id: text(form, "project_id"), name: text(form, "name"), environment: text(form, "environment") });
  revalidatePath("/manage");
}

export async function createBudget(form: FormData) {
  await adminMutate("/api/budgets", "POST", { scope_id: text(form, "scope_id"), limit_amount: Number(text(form, "limit_amount")), warning_threshold: Number(text(form, "warning_threshold") || 0.8), action_at_limit: text(form, "action_at_limit") });
  revalidatePath("/manage");
  revalidatePath("/budgets");
}

export async function testProvider(form: FormData) {
  await adminMutate(`/api/providers/${text(form, "provider_id")}/test`, "POST", {});
  revalidatePath("/providers");
}
