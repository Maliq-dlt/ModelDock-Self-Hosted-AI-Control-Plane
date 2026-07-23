import { adminFetch } from "../../lib/api";

type Model = { id: string; model_name: string; display_name: string | null; context_window: number; capabilities: string[]; pricing: Record<string, number>; enabled: boolean };

export default async function Models() {
  const models = await adminFetch<Model[]>("/api/models").catch(() => []);
  return <><header className="pageHeader"><div><p className="eyebrow">Registry</p><h1>Models</h1><p>Capabilities and pricing used by route decisions.</p></div></header><section className="panel"><div className="tableWrap"><table><thead><tr><th>Model</th><th>Context</th><th>Capabilities</th><th>Input / 1M</th><th>Output / 1M</th><th>Status</th></tr></thead><tbody>{models.length ? models.map(model => <tr key={model.id}><td><strong>{model.display_name ?? model.model_name}</strong><small className="block mono">{model.model_name}</small></td><td>{model.context_window.toLocaleString()}</td><td>{model.capabilities.join(", ")}</td><td>${(model.pricing.input_cost_per_million ?? 0).toFixed(2)}</td><td>${(model.pricing.output_cost_per_million ?? 0).toFixed(2)}</td><td><span className={`status ${model.enabled ? "success" : "error"}`}>{model.enabled ? "enabled" : "disabled"}</span></td></tr>) : <tr><td colSpan={6} className="empty">No models registered.</td></tr>}</tbody></table></div></section></>;
}
