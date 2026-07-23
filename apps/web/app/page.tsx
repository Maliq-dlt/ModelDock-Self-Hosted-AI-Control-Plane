import { adminFetch, Trace, UsageSummary } from "../lib/api";

type Timeseries = { date: string; requests: number; tokens: number; estimated_cost: number };
type Breakdown = { provider?: string; model?: string; requests: number; estimated_cost: number };

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <article className="metric"><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}

export default async function Overview() {
  const [usage, traces, timeseries, providers, models] = await Promise.all([
    adminFetch<UsageSummary>("/api/usage/summary").catch(() => ({ requests: 0, total_tokens: 0, estimated_cost: 0, average_latency_ms: 0, errors: 0 })),
    adminFetch<Trace[]>("/api/traces?limit=8").catch(() => []),
    adminFetch<Timeseries[]>("/api/usage/timeseries?days=14").catch(() => []),
    adminFetch<Breakdown[]>("/api/usage/by-provider").catch(() => []),
    adminFetch<Breakdown[]>("/api/usage/by-model").catch(() => []),
  ]);
  const maxRequests = Math.max(1, ...timeseries.map(item => item.requests));
  return <>
    <header className="pageHeader"><div><p className="eyebrow">Control plane</p><h1>AI traffic, under control.</h1><p>Routing, spend, latency, and failures across every provider.</p></div><span className="live"><i /> System live</span></header>
    <section className="metrics"><Metric label="Requests this month" value={usage.requests.toLocaleString()} detail={`${usage.errors} errors`} /><Metric label="Tokens" value={usage.total_tokens.toLocaleString()} detail="prompt + completion" /><Metric label="Estimated cost" value={`$${usage.estimated_cost.toFixed(4)}`} detail="current month" /><Metric label="Average latency" value={`${Math.round(usage.average_latency_ms)} ms`} detail="all providers" /></section>
    <section className="overviewGrid"><article className="panel chartPanel"><div className="panelHeader"><p className="eyebrow">14 days</p><h2>Request volume</h2></div><div className="barChart">{timeseries.length ? timeseries.map(item => <div className="barColumn" key={item.date}><div className="bar" style={{ height: `${Math.max(6, item.requests / maxRequests * 100)}%` }} title={`${item.requests} requests`} /><span>{item.date.slice(5)}</span></div>) : <div className="empty">No usage yet.</div>}</div></article><article className="panel breakdown"><div className="panelHeader"><p className="eyebrow">Spend split</p><h2>Providers</h2></div>{providers.slice(0, 5).map(item => <div className="breakdownRow" key={item.provider}><span>{item.provider}</span><strong>${item.estimated_cost.toFixed(4)}</strong></div>)}<div className="panelHeader second"><p className="eyebrow">Traffic split</p><h2>Models</h2></div>{models.slice(0, 5).map(item => <div className="breakdownRow" key={item.model}><span>{item.model}</span><strong>{item.requests}</strong></div>)}</article></section>
    <section className="panel"><div className="panelHeader"><div><p className="eyebrow">Live feed</p><h2>Recent requests</h2></div></div><div className="tableWrap"><table><thead><tr><th>Trace</th><th>Virtual model</th><th>Status</th><th>Tokens</th><th>Latency</th><th>Cost</th></tr></thead><tbody>{traces.length ? traces.map(trace => <tr key={trace.trace_id}><td className="mono">{trace.trace_id}</td><td>{trace.virtual_model}</td><td><span className={`status ${trace.status}`}>{trace.status}</span></td><td>{trace.total_tokens}</td><td>{trace.latency_ms ? `${Math.round(trace.latency_ms)} ms` : "-"}</td><td>${trace.estimated_cost.toFixed(5)}</td></tr>) : <tr><td colSpan={6} className="empty">No requests yet. Seed demo data, then call gateway.</td></tr>}</tbody></table></div></section>
  </>;
}
