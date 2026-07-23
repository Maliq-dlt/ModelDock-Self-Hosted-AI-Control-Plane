import Link from "next/link";
import { AgentTopology } from "../components/dashboard-agent-topology";
import { ConsumptionChart } from "../components/dashboard-consumption-chart";
import { TokenPolicyPanel } from "../components/dashboard-policy-panel";
import { adminFetch, Project, Provider, Trace, UsagePoint, UsageSummary, VirtualModel } from "../lib/api";

type Breakdown = { provider?: string; model?: string; requests: number; estimated_cost: number };
type Range = 7 | 14 | 30;

function compactNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: value >= 10_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function Metric({ label, value, detail, tone, index }: { label: string; value: string; detail: string; tone: string; index: number }) {
  return <article className={`metric metric${tone}`} style={{ animationDelay: `${index * 55}ms` }}><div className="metricTop"><span>{label}</span><i /></div><strong>{value}</strong><small>{detail}</small></article>;
}

function decisionText(trace?: Trace) {
  if (!trace) return { reason: "No receipt yet", selected: "Awaiting first route", lane: "idle" };
  const decision = (trace.metadata.routing_decision ?? trace.metadata) as Record<string, unknown>;
  const selected = (trace.metadata.selected ?? {}) as Record<string, unknown>;
  return {
    reason: String(decision.reason ?? decision.strategy ?? "priority route"),
    selected: [selected.provider, selected.model].filter(Boolean).join(" / ") || trace.virtual_model,
    lane: String(decision.canary_lane ?? trace.status),
  };
}

export default async function Overview({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const query = await searchParams;
  const days: Range = query.days === "7" || query.days === "30" ? Number(query.days) as Range : 14;
  const emptyUsage: UsageSummary = { requests: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, input_tokens_saved: 0, estimated_cost: 0, projected_monthly_cost: 0, average_latency_ms: 0, errors: 0 };
  const [usage, traces, timeseries, providers, models, projects, virtualModels] = await Promise.all([
    adminFetch<UsageSummary>("/api/usage/summary").catch(() => emptyUsage),
    adminFetch<Trace[]>("/api/traces?limit=10").catch(() => []),
    adminFetch<UsagePoint[]>(`/api/usage/timeseries?days=${days}`).catch(() => []),
    adminFetch<Provider[]>("/api/providers").catch(() => []),
    adminFetch<Breakdown[]>("/api/usage/by-model").catch(() => []),
    adminFetch<Project[]>("/api/projects").catch(() => []),
    adminFetch<VirtualModel[]>("/api/virtual-models").catch(() => []),
  ]);
  const healthyProviders = providers.filter(provider => provider.health_status === "healthy").length;
  const systemState = providers.some(provider => provider.health_status === "unhealthy") ? "degraded" : "nominal";
  const receipt = decisionText(traces[0]);
  const activeProject = projects[0] ?? null;
  const errorRate = usage.requests ? (usage.errors / usage.requests) * 100 : 0;

  return <div className="dashboard"><header className="commandHeader"><div><div className="titleLine"><span className="titleSigil">⌁</span><p className="eyebrow">Live control room</p></div><h1>Traffic has a shape.<br /><em>Make it intentional.</em></h1><p className="headerCopy">One operational view for agent routes, model consumption, policy state, and provider health.</p></div><div className="headerControls"><span className={`systemPill ${systemState}`}><i />{systemState}</span><div className="rangeSwitch" aria-label="Consumption range">{([7, 14, 30] as const).map(range => <Link href={`/?days=${range}`} className={range === days ? "active" : ""} key={range}>{range}D</Link>)}</div></div></header>

    <section className="metrics"><Metric index={0} tone="Amber" label="Requests" value={usage.requests.toLocaleString()} detail={`${usage.errors} errors · ${errorRate.toFixed(1)}%`} /><Metric index={1} tone="Blue" label="Input tokens" value={compactNumber(usage.input_tokens)} detail={`${compactNumber(usage.input_tokens_saved)} safely removed`} /><Metric index={2} tone="Mint" label="Output tokens" value={compactNumber(usage.output_tokens)} detail="No truncation applied" /><Metric index={3} tone="Paper" label="Estimated cost" value={`$${usage.estimated_cost.toFixed(3)}`} detail={`$${usage.projected_monthly_cost.toFixed(2)} projected`} /><Metric index={4} tone="Red" label="Latency" value={`${Math.round(usage.average_latency_ms)} ms`} detail={`${healthyProviders}/${providers.length} runtimes healthy`} /></section>

    <section className="dashboardGrid upperGrid"><ConsumptionChart points={timeseries} /><TokenPolicyPanel project={activeProject} /></section>

    <section className="decisionStrip"><div className="receiptStamp"><span>DR</span><small>Decision receipt</small></div><div><p className="eyebrow">Why latest route won</p><h2>{receipt.reason}</h2><p>{receipt.selected}</p></div><div className="receiptFacts"><span>Lane<strong>{receipt.lane}</strong></span><span>Trace<strong>{traces[0]?.trace_id.slice(-8) ?? "—"}</strong></span><span>Replay<strong>{traces[0] ? "ready" : "idle"}</strong></span></div>{traces[0] && <Link href={`/traces/${traces[0].trace_id}`} className="receiptLink">Open receipt ↗</Link>}</section>

    <section className="dashboardGrid lowerGrid"><AgentTopology providers={providers} virtualModels={virtualModels} /><article className="panel recentPanel"><div className="panelHeader chartHeader"><div><p className="eyebrow">Request ledger</p><h2>Recent traffic</h2></div><Link href="/traces" className="textLink">All traces ↗</Link></div><div className="requestList">{traces.length ? traces.map(trace => <Link href={`/traces/${trace.trace_id}`} className="requestRow" key={trace.trace_id}><span className={`requestState ${trace.status}`} /><div><strong>{trace.virtual_model}</strong><small className="mono">{trace.trace_id}</small></div><span className="tokenPair"><b>{compactNumber(trace.prompt_tokens)}</b><i>/</i><b>{compactNumber(trace.completion_tokens)}</b><small>in / out</small></span><span className="requestCost">${trace.estimated_cost.toFixed(4)}<small>{trace.latency_ms ? `${Math.round(trace.latency_ms)} ms` : "pending"}</small></span></Link>) : <div className="emptyLedger"><span>∅</span><strong>No requests recorded</strong><small>Send traffic through gateway to populate ledger.</small></div>}</div><div className="modelTicker">{models.slice(0, 4).map(model => <span key={model.model}><i />{model.model}<strong>{model.requests}</strong></span>)}</div></article></section>
  </div>;
}
