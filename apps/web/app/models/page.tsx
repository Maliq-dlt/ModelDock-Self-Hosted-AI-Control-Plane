import Link from "next/link";
import { adminFetch } from "../../lib/api";

type Model = { id: string; provider_id: string; model_name: string; display_name: string | null; context_window: number; capabilities: string[]; pricing: Record<string, number>; tags: string[]; enabled: boolean };
type Provider = { id: string; name: string };

export default async function Models() {
  const [models, providers] = await Promise.all([adminFetch<Model[]>("/api/models").catch(() => []), adminFetch<Provider[]>("/api/providers").catch(() => [])]);
  const providerNames = new Map(providers.map((provider) => [provider.id, provider.name]));
  return <><header className="pageHeader"><div><p className="eyebrow">Model registry</p><h1>Every model, explained.</h1><p>Capabilities and pricing feed routing decisions. Edit provider inventory from setup center.</p></div><Link href="/manage#model" className="primaryButton">Add model<span>+</span></Link></header><section className="modelGrid">{models.length ? models.map((model) => <article className="modelCard softCard" key={model.id}><div className="modelCardTop"><span className="modelGlyph">AI</span><span className={`status ${model.enabled ? "success" : "error"}`}>{model.enabled ? "enabled" : "disabled"}</span></div><h2>{model.display_name ?? model.model_name}</h2><p className="mono">{model.model_name}</p><div className="chipRow"><span>{providerNames.get(model.provider_id) ?? "Unknown provider"}</span>{model.capabilities.map((capability) => <span key={capability}>{capability}</span>)}</div><dl><div><dt>Context</dt><dd>{model.context_window.toLocaleString()} tokens</dd></div><div><dt>Input</dt><dd>${(model.pricing.input_cost_per_million ?? 0).toFixed(2)} / 1M</dd></div><div><dt>Output</dt><dd>${(model.pricing.output_cost_per_million ?? 0).toFixed(2)} / 1M</dd></div></dl></article>) : <div className="emptyState"><span>MD</span><h2>No models registered</h2><p>Connect provider first, then add exact model ID.</p><Link href="/manage#model" className="primaryButton">Add first model<span>+</span></Link></div>}</section></>;
}
