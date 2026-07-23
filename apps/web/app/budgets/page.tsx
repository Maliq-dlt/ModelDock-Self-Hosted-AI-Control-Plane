import Link from "next/link";
import { createBudget } from "../actions";
import { adminFetch } from "../../lib/api";

type Budget = { id: string; scope_id: string; period: string; limit_amount: number; warning_threshold: number; action_at_limit: string };
type Project = { id: string; name: string };
type ProjectUsage = { project_id: string; estimated_cost: number; requests: number; total_tokens: number };

export default async function Budgets() {
  const [budgets, projects, usage] = await Promise.all([adminFetch<Budget[]>("/api/budgets").catch(() => []), adminFetch<Project[]>("/api/projects").catch(() => []), adminFetch<ProjectUsage[]>("/api/usage/by-project").catch(() => [])]);
  const projectNames = new Map(projects.map((project) => [project.id, project.name]));
  const usageByProject = new Map(usage.map((item) => [item.project_id, item]));

  return <><header className="pageHeader"><div><p className="eyebrow">Quota tracker</p><h1>Spend limits without spreadsheet work.</h1><p>See monthly pace, warning point, and enforcement behavior per workspace.</p></div><Link href="#new-budget" className="primaryButton">Add quota<span>+</span></Link></header>
    <section className="quotaGrid">{budgets.length ? budgets.map((budget) => { const current = usageByProject.get(budget.scope_id)?.estimated_cost ?? 0; const percent = budget.limit_amount ? Math.min(100, (current / budget.limit_amount) * 100) : 0; const warning = percent >= budget.warning_threshold * 100; return <article className="quotaCard softCard" key={budget.id}><div className="quotaTop"><div><p className="eyebrow">{projectNames.get(budget.scope_id) ?? "Workspace"}</p><h2>${current.toFixed(2)} <small>/ ${budget.limit_amount.toFixed(2)}</small></h2></div><span className={`status ${warning ? "pending" : "success"}`}>{warning ? "watch" : "on track"}</span></div><div className="quotaTrack"><i style={{ width: `${percent}%` }} /></div><div className="quotaFacts"><span><small>Used</small><strong>{percent.toFixed(1)}%</strong></span><span><small>Warning</small><strong>{Math.round(budget.warning_threshold * 100)}%</strong></span><span><small>At limit</small><strong>{budget.action_at_limit}</strong></span></div></article>; }) : <div className="emptyState"><span>QT</span><h2>No quota configured</h2><p>Add a monthly project limit. ModelDock checks it before provider call.</p></div>}</section>
    <section className="inlineFormPanel" id="new-budget"><div><p className="eyebrow">New monthly quota</p><h2>Set a guardrail</h2><p>Start with warning mode if you want observation before blocking.</p></div><form action={createBudget}><label><span>Workspace</span><select name="scope_id" required>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label><span>Limit USD</span><input name="limit_amount" type="number" min="0.01" step="0.01" placeholder="100" required /></label><label><span>Warn at</span><select name="warning_threshold" defaultValue="0.8"><option value="0.5">50%</option><option value="0.8">80%</option><option value="0.9">90%</option></select></label><label><span>At limit</span><select name="action_at_limit" defaultValue="block"><option value="block">Block new requests</option><option value="warn">Warn only</option></select></label><button type="submit" disabled={!projects.length}>Save quota</button></form></section>
  </>;
}
