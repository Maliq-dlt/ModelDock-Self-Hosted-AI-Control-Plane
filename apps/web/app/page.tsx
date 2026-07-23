import Link from "next/link";
import { AgentTopology } from "../components/dashboard-agent-topology";
import { ConsumptionChart } from "../components/dashboard-consumption-chart";
import { TokenPolicyPanel } from "../components/dashboard-policy-panel";
import { adminFetch, ApiKey, Project, Provider, Trace, UsagePoint, UsageSummary, VirtualModel } from "../lib/api";

type Breakdown = { provider?: string; model?: string; requests: number; estimated_cost: number };
type ModelRecord = { id: string; model_name: string; display_name: string | null };
type Range = 7 | 14 | 30;

type SetupStep = { number: string; title: string; detail: string; href: string; done: boolean; action: string };

function compactNumber(value: number) {
  return new Intl.NumberFormat("en", { notation: value >= 10_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

function Metric({ label, value, detail, tone, index }: { label: string; value: string; detail: string; tone: string; index: number }) {
  return <article className={`metric metric${tone}`} style={{ animationDelay: `${index * 55}ms` }}><div className="metricTop"><span>{label}</span><i /></div><strong>{value}</strong><small>{detail}</small></article>;
}

function decisionText(trace?: Trace) {
  if (!trace) return { reason: "No route receipt yet", selected: "Your first request will appear here", lane: "waiting" };
  const decision = (trace.metadata.routing_decision ?? trace.metadata) as Record<string, unknown>;
  const selected = (trace.metadata.selected ?? {}) as Record<string, unknown>;
  return {
    reason: String(decision.reason ?? decision.strategy ?? "priority route"),
    selected: [selected.provider, selected.model].filter(Boolean).join(" / ") || trace.virtual_model,
    lane: String(decision.canary_lane ?? trace.status),
  };
}

function SetupPanel({ steps, complete }: { steps: SetupStep[]; complete: boolean }) {
  const doneCount = steps.filter((step) => step.done).length;
  return <section className={`setupPanel ${complete ? "setupComplete" : ""}`}>
    <div className="setupIntro"><span className="setupOrb">{complete ? "OK" : `${doneCount}/${steps.length}`}</span><div><p className="eyebrow">Workspace setup</p><h2>{complete ? "Ready for traffic" : "Get your first route live"}</h2><p>{complete ? "Core control plane pieces are connected. Tune policies when needed." : "Four short steps. No config files needed."}</p></div></div>
    <div className="setupSteps">{steps.map((step) => <Link href={step.href} className={`setupStep ${step.done ? "done" : ""}`} key={step.number}><span className="stepNumber">{step.done ? "OK" : step.number}</span><span><strong>{step.title}</strong><small>{step.done ? "Complete" : step.detail}</small></span><b>{step.done ? "Done" : step.action}</b></Link>)}</div>
  </section>;
}

export default async function Overview({ searchParams }: { searchParams: Promise<{ days?: string }> }) {
  const query = await searchParams;
  const days: Range = query.days === "7" || query.days === "30" ? Number(query.days) as Range : 14;
  const emptyUsage: UsageSummary = { requests: 0, input_tokens: 0, output_tokens: 0, total_tokens: 0, input_tokens_saved: 0, estimated_cost: 0, projected_monthly_cost: 0, average_latency_ms: 0, errors: 0 };
  const [usage, traces, timeseries, providers, modelUsage, projects, virtualModels, models, apiKeys] = await Promise.all([
    adminFetch<UsageSummary>("/api/usage/summary").catch(() => emptyUsage),
    adminFetch<Trace[]>("/api/traces?limit=10").catch(() => []),
    adminFetch<UsagePoint[]>(`/api/usage/timeseries?days=${days}`).catch(() => []),
    adminFetch<Provider[]>("/api/providers").catch(() => []),
    adminFetch<Breakdown[]>("/api/usage/by-model").catch(() => []),
    adminFetch<Project[]>("/api/projects").catch(() => []),
    adminFetch<VirtualModel[]>("/api/virtual-models").catch(() => []),
    adminFetch<ModelRecord[]>("/api/models").catch(() => []),
    adminFetch<ApiKey[]>("/api/api-keys").catch(() => []),
  ]);
  const healthyProviders = providers.filter((provider) => provider.health_status === "healthy").length;
  const systemState = providers.some((provider) => provider.health_status === "unhealthy") ? "degraded" : "nominal";
  const receipt = decisionText(traces[0]);
  const activeProject = projects[0] ?? null;
  const errorRate = usage.requests ? (usage.errors / usage.requests) * 100 : 0;
  const steps: SetupStep[] = [
    { number: "01", title: "Create workspace", detail: "Name your first project", href: "/manage#project", done: projects.length > 0, action: "Start" },
    { number: "02", title: "Connect provider", detail: "Add Ollama or cloud model", href: "/manage#provider", done: providers.length > 0, action: "Connect" },
    { number: "03", title: "Add model", detail: "Register model capability", href: "/manage#model", done: models.length > 0, action: "Add" },
    { number: "04", title: "Create route", detail: "Give apps one stable alias", href: "/manage#route", done: virtualModels.length > 0, action: "Route" },
    { number: "05", title: "Issue API key", detail: "Connect your first app", href: "/keys", done: apiKeys.length > 0, action: "Create" },
  ];
  const setupComplete = steps.every((step) => step.done);

  return <div className="dashboard">
    <header className="welcomeHeader">
      <div><p className="eyebrow">Workspace overview</p><h1>Your AI traffic,<br /><em>without guesswork.</em></h1><p className="headerCopy">Route requests. Watch provider health. Control token behavior from one calm workspace.</p></div>
      <div className="headerActions"><span className={`systemPill ${systemState}`}><i />{systemState === "nominal" ? "All systems ready" : "Needs attention"}</span><Link className="primaryButton" href={setupComplete ? "/routing" : "/manage"}>{setupComplete ? "Tune routing" : "Finish setup"}<span>+</span></Link></div>
    </header>

    <SetupPanel steps={steps} complete={setupComplete} />

    <section className="metrics"><Metric index={0} tone="Amber" label="Requests this month" value={usage.requests.toLocaleString()} detail={`${usage.errors} errors / ${errorRate.toFixed(1)}% error rate`} /><Metric index={1} tone="Blue" label="Input tokens" value={compactNumber(usage.input_tokens)} detail={`${compactNumber(usage.input_tokens_saved)} saved by Token Saver`} /><Metric index={2} tone="Mint" label="Output tokens" value={compactNumber(usage.output_tokens)} detail="Output stays complete" /><Metric index={3} tone="Paper" label="Estimated cost" value={`$${usage.estimated_cost.toFixed(3)}`} detail={`$${usage.projected_monthly_cost.toFixed(2)} projected this month`} /></section>

    <section className="dashboardGrid upperGrid"><ConsumptionChart points={timeseries} /><TokenPolicyPanel project={activeProject} /></section>

    <section className="decisionStrip"><div className="receiptStamp"><span>DR</span><small>Decision receipt</small></div><div><p className="eyebrow">Why latest route won</p><h2>{receipt.reason}</h2><p>{receipt.selected}</p></div><div className="receiptFacts"><span>Lane<strong>{receipt.lane}</strong></span><span>Trace<strong>{traces[0]?.trace_id.slice(-8) ?? "none"}</strong></span><span>Replay<strong>{traces[0] ? "ready" : "waiting"}</strong></span></div>{traces[0] && <Link href={`/traces/${traces[0].trace_id}`} className="receiptLink">Open receipt</Link>}</section>

    <section className="dashboardGrid lowerGrid"><AgentTopology providers={providers} virtualModels={virtualModels} /><article className="panel recentPanel"><div className="panelHeader chartHeader"><div><p className="eyebrow">Request ledger</p><h2>Recent traffic</h2></div><Link href="/traces" className="textLink">All traces</Link></div><div className="requestList">{traces.length ? traces.map((trace) => <Link href={`/traces/${trace.trace_id}`} className="requestRow" key={trace.trace_id}><span className={`requestState ${trace.status}`} /><div><strong>{trace.virtual_model}</strong><small className="mono">{trace.trace_id}</small></div><span className="tokenPair"><b>{compactNumber(trace.prompt_tokens)}</b><i>/</i><b>{compactNumber(trace.completion_tokens)}</b><small>in / out</small></span><span className="requestCost">${trace.estimated_cost.toFixed(4)}<small>{trace.latency_ms ? `${Math.round(trace.latency_ms)} ms` : "pending"}</small></span></Link>) : <div className="emptyLedger"><span>--</span><strong>No requests yet</strong><small>Send traffic through your gateway to populate this ledger.</small></div>}</div><div className="modelTicker">{modelUsage.slice(0, 4).map((model) => <span key={model.model}><i />{model.model}<strong>{model.requests}</strong></span>)}</div></article></section>

    <section className="quickActions"><Link href="/providers"><span className="quickIcon">PV</span><span><strong>Connect another provider</strong><small>Cloud or local runtime</small></span><b>Open</b></Link><Link href="/token-saver"><span className="quickIcon">TS</span><span><strong>Protect your token budget</strong><small>Safe, Caveman, Ponytail</small></span><b>Open</b></Link><Link href="/cli-tools"><span className="quickIcon">CL</span><span><strong>Send your first request</strong><small>Copy a ready-to-run command</small></span><b>Open</b></Link></section>
  </div>;
}
