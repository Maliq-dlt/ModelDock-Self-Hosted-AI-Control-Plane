import Link from "next/link";
import { adminFetch, VirtualModel } from "../../lib/api";

type Project = { id: string; name: string };
type Model = { id: string; model_name: string; display_name: string | null };

const strategyCopy: Record<string, string> = {
  priority: "Primary model first, then automatic fallback.",
  cheapest: "Lowest configured token price wins.",
  fastest: "Lowest recent provider latency wins.",
  weighted_random: "Traffic follows candidate weights.",
  weighted_score: "Balances health, quality, speed, and cost.",
  canary: "Stable traffic split for controlled rollout.",
};

export default async function Routing() {
  const [routes, projects, models] = await Promise.all([adminFetch<VirtualModel[]>("/api/virtual-models").catch(() => []), adminFetch<Project[]>("/api/projects").catch(() => []), adminFetch<Model[]>("/api/models").catch(() => [])]);
  const projectNames = new Map(projects.map((project) => [project.id, project.name]));
  const modelNames = new Map(models.map((model) => [model.id, model.display_name ?? model.model_name]));
  return <><header className="pageHeader"><div><p className="eyebrow">Routing</p><h1>One model name. Many ways to serve it.</h1><p>Apps call a stable alias while ModelDock handles provider choice, fallback, and canary traffic.</p></div><Link href="/manage#route" className="primaryButton">Create route<span>+</span></Link></header><section className="routeGrid">{routes.length ? routes.map((route) => <article className="routeCard softCard" key={route.id}><div className="routeTop"><span className="routeGlyph">RT</span><span className={`status ${route.enabled ? "success" : "error"}`}>{route.enabled ? "live" : "paused"}</span></div><p className="eyebrow">{projectNames.get(route.project_id) ?? "Workspace"}</p><h2>{route.name}</h2><p>{strategyCopy[route.strategy] ?? route.strategy}</p><div className="strategyBadge">{route.strategy.replaceAll("_", " ")}</div><div className="candidateList">{route.candidates.map((candidate, index) => <span key={`${route.id}-${index}`}><b>{index + 1}</b>{modelNames.get(candidate.model_id ?? "") ?? candidate.model ?? "Unknown model"}</span>)}</div>{route.strategy === "canary" && <small>Canary traffic: {route.strategy_config.canary_percent ?? 5}%</small>}</article>) : <div className="emptyState"><span>RT</span><h2>No routes yet</h2><p>Create a stable alias after registering your first model.</p><Link href="/manage#route" className="primaryButton">Create first route<span>+</span></Link></div>}</section></>;
}
