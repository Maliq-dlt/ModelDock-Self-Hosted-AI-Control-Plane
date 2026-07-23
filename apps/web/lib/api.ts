const apiUrl = process.env.MODELDOCK_API_URL ?? "http://localhost:8080";
const adminKey = process.env.MODELDOCK_ADMIN_API_KEY ?? "";

export async function adminFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    headers: { "X-ModelDock-Admin-Key": adminKey },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`ModelDock API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export type TokenPolicy = {
  safe: boolean;
  caveman: boolean;
  ponytail: boolean;
};

export type Project = {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  token_policy: TokenPolicy;
};

export type Provider = {
  id: string;
  name: string;
  provider_type: string;
  enabled: boolean;
  health_status: string;
  last_health_latency_ms: number | null;
};

export type VirtualModel = {
  id: string;
  project_id: string;
  name: string;
  strategy: string;
  candidates: Array<{ model_id?: string; model?: string }>;
  strategy_config: Record<string, number>;
  enabled: boolean;
};

export type UsageSummary = {
  requests: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  input_tokens_saved: number;
  estimated_cost: number;
  projected_monthly_cost: number;
  average_latency_ms: number;
  errors: number;
};

export type UsagePoint = {
  date: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  tokens: number;
  estimated_cost: number;
};

export type Trace = {
  trace_id: string;
  project_id: string;
  virtual_model: string;
  status: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  estimated_cost: number;
  latency_ms: number | null;
  started_at: string;
  metadata: Record<string, unknown>;
};

export async function adminMutate<T>(path: string, method: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiUrl}${path}`, {
    method,
    headers: { "X-ModelDock-Admin-Key": adminKey, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`ModelDock API returned ${response.status}: ${await response.text()}`);
  }
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}
