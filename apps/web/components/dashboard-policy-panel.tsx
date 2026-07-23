import { updateTokenPolicy } from "../app/actions";
import type { Project } from "../lib/api";

type Props = { project: Project | null };

export function TokenPolicyPanel({ project }: Props) {
  if (!project) return <article className="panel policyPanel"><div className="panelHeader"><div><p className="eyebrow">Output guardrails</p><h2>Token Saver</h2></div></div><div className="panelBody emptyPolicy"><strong>Create workspace first.</strong><span>Policy attaches to project traffic.</span><a href="/manage">Open setup center</a></div></article>;
  const policy = project.token_policy;
  const enabled = [policy.safe, policy.caveman, policy.ponytail].filter(Boolean).length;
  const effective = policy.caveman && policy.ponytail ? "stacked" : policy.caveman ? "caveman" : policy.ponytail ? "ponytail" : policy.safe ? "safe" : "off";
  return <article className="panel policyPanel"><div className="panelHeader policyHeader"><div><p className="eyebrow">Output guardrails</p><h2>Token Saver</h2><small>Input gets smaller. Output stays complete.</small></div><span className="policyMode">{effective}</span></div><form action={updateTokenPolicy} className="policyForm"><input type="hidden" name="project_id" value={project.id} /><label className="switchRow"><span className="switchCopy"><strong>Safe</strong><small>Clean repeated whitespace and tool payload noise</small></span><input type="checkbox" name="safe" defaultChecked={policy.safe} /><span className="switchTrack" aria-hidden="true"><i /></span></label><label className="switchRow"><span className="switchCopy"><strong>Caveman</strong><small>Short language, full technical detail</small></span><input type="checkbox" name="caveman" defaultChecked={policy.caveman} /><span className="switchTrack" aria-hidden="true"><i /></span></label><label className="switchRow"><span className="switchCopy"><strong>Ponytail</strong><small>Smallest sufficient code change</small></span><input type="checkbox" name="ponytail" defaultChecked={policy.ponytail} /><span className="switchTrack" aria-hidden="true"><i /></span></label><div className="policyBottom"><span>{enabled}/3 modes active / output untouched</span><button type="submit">Save for {project.name}</button></div></form></article>;
}
