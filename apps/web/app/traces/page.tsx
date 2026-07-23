import Link from "next/link";
import { adminFetch, Trace } from "../../lib/api";

export default async function Traces({ searchParams }: { searchParams: Promise<{ status?: string; model?: string; page?: string }> }) {
  const filters = await searchParams;
  const query = new URLSearchParams({ limit: "50", page: filters.page ?? "1" });
  if (filters.status) query.set("status", filters.status);
  if (filters.model) query.set("virtual_model", filters.model);
  const traces = await adminFetch<Trace[]>(`/api/traces?${query}`).catch(() => []);
  return <><header className="pageHeader"><div><p className="eyebrow">Observability</p><h1>Request traces</h1><p>Every routing decision, retry, fallback, and provider result.</p></div></header><form className="filterBar"><select name="status" defaultValue={filters.status ?? ""}><option value="">All statuses</option><option value="success">Success</option><option value="error">Error</option><option value="blocked">Blocked</option></select><input name="model" defaultValue={filters.model ?? ""} placeholder="Virtual model" /><button type="submit">Filter</button></form><section className="panel"><div className="tableWrap"><table><thead><tr><th>Trace</th><th>Model</th><th>Status</th><th>Tokens</th><th>Latency</th><th>Cost</th><th>Started</th></tr></thead><tbody>{traces.length ? traces.map(trace => <tr key={trace.trace_id}><td><Link href={`/traces/${trace.trace_id}`} className="mono traceLink">{trace.trace_id}</Link></td><td>{trace.virtual_model}</td><td><span className={`status ${trace.status}`}>{trace.status}</span></td><td>{trace.total_tokens}</td><td>{trace.latency_ms ? `${Math.round(trace.latency_ms)} ms` : "-"}</td><td>${trace.estimated_cost.toFixed(5)}</td><td>{new Date(trace.started_at).toLocaleString()}</td></tr>) : <tr><td colSpan={7} className="empty">No traces match filter.</td></tr>}</tbody></table></div></section></>;
}
