import Link from "next/link";
import { testProvider } from "../actions";
import { adminFetch } from "../../lib/api";

type Provider = { id: string; name: string; provider_type: string; base_url: string | null; enabled: boolean; has_credentials: boolean; health_status: string; last_health_checked_at: string | null; last_health_latency_ms: number | null; reliability_score?: number };

function providerTone(status: string) {
  return status === "healthy" ? "success" : status === "unhealthy" ? "error" : "pending";
}

export default async function Providers() {
  const providers = await adminFetch<Provider[]>("/api/providers").catch(() => []);
  const healthy = providers.filter((provider) => provider.health_status === "healthy").length;

  return <><header className="pageHeader"><div><p className="eyebrow">Provider connections</p><h1>Models start with a healthy connection.</h1><p>Cloud APIs and local runtimes live together. Credentials never return to browser.</p></div><Link href="/manage#provider" className="primaryButton">Connect provider<span>+</span></Link></header>
    <section className="summaryBar"><span><strong>{providers.length}</strong> connected</span><span><strong>{healthy}</strong> healthy</span><span><strong>{providers.length - healthy}</strong> need check</span></section>
    <section className="providerGrid">{providers.length ? providers.map((provider) => <article className="providerCard softCard" key={provider.id}><div className="providerCardTop"><div className="providerIdentity"><div className="providerIcon">{provider.name.slice(0, 2).toUpperCase()}</div><div><h2>{provider.name}</h2><p>{provider.provider_type.replaceAll("_", " ")}</p></div></div><span className={`status ${providerTone(provider.health_status)}`}><i />{provider.health_status === "unknown" ? "not tested" : provider.health_status}</span></div><dl><div><dt>Endpoint</dt><dd>{provider.base_url ?? "Provider default"}</dd></div><div><dt>Credentials</dt><dd>{provider.has_credentials ? "Encrypted and ready" : "Not required"}</dd></div><div><dt>Last check</dt><dd>{provider.last_health_checked_at ? `${new Date(provider.last_health_checked_at).toLocaleString()} / ${Math.round(provider.last_health_latency_ms ?? 0)} ms` : "Run connection test"}</dd></div></dl><form action={testProvider} className="cardAction"><input type="hidden" name="provider_id" value={provider.id} /><button type="submit">Test connection</button><Link href="/models">View models</Link></form></article>) : <div className="emptyState"><span>PV</span><h2>No providers connected</h2><p>Start with Ollama for local inference or connect a cloud API.</p><Link href="/manage#provider" className="primaryButton">Connect first provider<span>+</span></Link></div>}</section>
  </>;
}
