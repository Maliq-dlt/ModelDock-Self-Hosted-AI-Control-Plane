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

export type UsageSummary = {
  requests: number;
  total_tokens: number;
  estimated_cost: number;
  average_latency_ms: number;
  errors: number;
};

export type Trace = {
  trace_id: string;
  virtual_model: string;
  status: string;
  total_tokens: number;
  estimated_cost: number;
  latency_ms: number | null;
  started_at: string;
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
