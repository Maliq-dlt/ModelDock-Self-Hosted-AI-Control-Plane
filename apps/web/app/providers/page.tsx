import { testProvider } from "../actions";
import { adminFetch } from "../../lib/api";

type Provider = { id: string; name: string; provider_type: string; base_url: string | null; enabled: boolean; has_credentials: boolean; health_status: string; last_health_checked_at: string | null; last_health_latency_ms: number | null };

export default async function Providers() {
  const providers = await adminFetch<Provider[]>("/api/providers").catch(() => []);
  return <><header className="pageHeader"><div><p className="eyebrow">Registry</p><h1>Providers</h1><p>Cloud and local inference endpoints available to routing.</p></div></header><section className="cardGrid">{providers.length ? providers.map(provider => <article className="providerCard" key={provider.id}><div className="providerIcon">{provider.name.slice(0, 2).toUpperCase()}</div><div><h2>{provider.name}</h2><p>{provider.provider_type.replaceAll("_", " ")}</p></div><span className={`status ${provider.health_status === "healthy" ? "success" : provider.health_status === "unhealthy" ? "error" : "pending"}`}>{provider.health_status}</span><dl><dt>Endpoint</dt><dd>{provider.base_url ?? "provider default"}</dd><dt>Credentials</dt><dd>{provider.has_credentials ? "encrypted" : "not required"}</dd><dt>Last check</dt><dd>{provider.last_health_checked_at ? `${new Date(provider.last_health_checked_at).toLocaleString()} / ${Math.round(provider.last_health_latency_ms ?? 0)} ms` : "not tested"}</dd></dl><form action={testProvider} className="cardAction"><input type="hidden" name="provider_id" value={provider.id} /><button type="submit">Test connection</button></form></article>) : <div className="emptyCard">No providers registered.</div>}</section></>;
}
