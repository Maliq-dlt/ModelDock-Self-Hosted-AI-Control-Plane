import { TokenPolicyPanel } from "../../components/dashboard-policy-panel";
import { adminFetch, Project } from "../../lib/api";

const modes = [
  { name: "Safe", tone: "blue", detail: "Lossless cleanup for repeated whitespace, tool payload noise, and safe request structure." },
  { name: "Caveman", tone: "amber", detail: "Short language. Full technical detail. Good for direct operational replies." },
  { name: "Ponytail", tone: "mint", detail: "Smallest sufficient code change. Good for focused repository work." },
];

export default async function TokenSaver() {
  const projects = await adminFetch<Project[]>("/api/projects").catch(() => []);
  const project = projects[0] ?? null;
  return <><header className="pageHeader"><div><p className="eyebrow">Token Saver</p><h1>Spend less on input.<br /><em>Keep output whole.</em></h1><p>Choose behavior once per workspace. Requests inherit it unless they set an explicit mode.</p></div></header><section className="tokenSaverLayout"><TokenPolicyPanel project={project} /><aside className="panel tokenExplainer"><p className="eyebrow">One rule</p><h2>Compression never means truncation.</h2><p>ModelDock reduces avoidable input tokens. It does not cut model output, tool calls, or technical detail.</p><div className="modeList">{modes.map((mode) => <div className={`modeCard ${mode.tone}`} key={mode.name}><span>{mode.name.slice(0, 2)}</span><p><strong>{mode.name}</strong><small>{mode.detail}</small></p></div>)}</div></aside></section><section className="panel requestOverride"><div><p className="eyebrow">Per-request override</p><h2>Need a different mode?</h2><p>Send `modeldock.token_mode` as `off`, `safe`, `caveman`, `ponytail`, or `stacked`. `inherit` uses workspace policy.</p></div><pre>{`{
  "model": "smart-router",
  "modeldock": { "token_mode": "safe" }
}`}</pre></section></>;
}
