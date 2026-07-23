import { adminFetch } from "../../lib/api";

type Budget = { id: string; scope_id: string; period: string; limit_amount: number; warning_threshold: number; action_at_limit: string };

export default async function Budgets() {
  const budgets = await adminFetch<Budget[]>("/api/budgets").catch(() => []);
  return <><header className="pageHeader"><div><p className="eyebrow">Governance</p><h1>Budgets</h1><p>Monthly project limits enforced before provider calls.</p></div></header><section className="cardGrid">{budgets.length ? budgets.map(budget => <article className="providerCard" key={budget.id}><div className="providerIcon">$</div><div><h2>${budget.limit_amount.toFixed(2)}</h2><p>{budget.period} project budget</p></div><span className="status success">{budget.action_at_limit}</span><dl><dt>Project</dt><dd className="mono">{budget.scope_id}</dd><dt>Warning</dt><dd>{Math.round(budget.warning_threshold * 100)}%</dd></dl></article>) : <div className="emptyCard">No budgets configured.</div>}</section></>;
}
