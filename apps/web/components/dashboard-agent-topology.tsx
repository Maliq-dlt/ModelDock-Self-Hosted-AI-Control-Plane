import type { Provider, VirtualModel } from "../lib/api";

type Props = { providers: Provider[]; virtualModels: VirtualModel[] };
type Position = { x: number; y: number };
const agentPositions: Position[] = [{ x: 17, y: 16 }, { x: 50, y: 8 }, { x: 83, y: 16 }, { x: 29, y: 34 }];
const providerPositions: Position[] = [{ x: 12, y: 76 }, { x: 35, y: 88 }, { x: 65, y: 88 }, { x: 88, y: 76 }, { x: 50, y: 96 }];

function statusClass(status: string) {
  return status === "healthy" ? "topologyHealthy" : status === "unhealthy" ? "topologyError" : "topologyPending";
}

export function AgentTopology({ providers, virtualModels }: Props) {
  const agents = virtualModels.slice(0, agentPositions.length);
  const providerNodes = providers.slice(0, providerPositions.length);
  return <article className="panel topologyPanel"><div className="panelHeader chartHeader"><div><p className="eyebrow">Agent fabric</p><h2>Connected routes</h2></div><span className="microBadge">{virtualModels.length} routes / {providers.length} runtimes</span></div><div className="topologyStage"><svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" className="topologyLines">{agents.map((_, index) => <line key={`a-${index}`} x1={agentPositions[index].x} y1={agentPositions[index].y + 7} x2="50" y2="53" className="topologyLink topologyAgentLink" />)}{providerNodes.map((_, index) => <line key={`p-${index}`} x1="50" y1="61" x2={providerPositions[index].x} y2={providerPositions[index].y - 5} className="topologyLink topologyProviderLink" />)}</svg><div className="topologyCore"><span className="coreOrb">MD</span><strong>Dock core</strong><small>route / learn / protect</small></div>{agents.map((agent, index) => <div key={agent.id} className="topologyNode agentNode" style={{ left: `${agentPositions[index].x}%`, top: `${agentPositions[index].y}%` }}><span className="nodeGlyph">RT</span><div><strong>{agent.name}</strong><small>{agent.strategy}{agent.strategy === "canary" ? ` / ${agent.strategy_config.canary_percent ?? 5}%` : ""}</small></div></div>)}{providerNodes.map((provider, index) => <div key={provider.id} className={`topologyNode providerNode ${statusClass(provider.health_status)}`} style={{ left: `${providerPositions[index].x}%`, top: `${providerPositions[index].y}%` }}><span className="nodePulse" /><div><strong>{provider.name}</strong><small>{provider.provider_type.replaceAll("_", " ")}</small></div></div>)}{!providers.length && <div className="topologyEmpty">Connect a provider to wake this fabric.</div>}</div><div className="topologyFooter"><span><i className="dot dotAgent" />Route</span><span><i className="dot dotProvider" />Provider</span><span><i className="dot dotHealthy" />Health pulse</span></div></article>;
}
