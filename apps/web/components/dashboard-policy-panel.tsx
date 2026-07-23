import { updateTokenPolicy } from "../app/actions";
import type { Project } from "../lib/api";

type Props = { project: Project | null };

export function TokenPolicyPanel({ project }: Props) {
  if (!project) {
    return <article className="panel policyPanel"><div className="panelHeader"><p className="eyebrow">Output guardrails</p><h2>TokenPress policy</h2></div><div className="panelBody emptyPolicy">Create project first. Policy attaches to project traffic.</div></article>;
  }
  const policy = project.token_policy;
  const enabled = [policy.safe, policy.caveman, policy.ponytail].filter(Boolean).length;
  const effective = policy.caveman && policy.ponytail ? "stacked" : policy.caveman ? "caveman" : policy.ponytail ? "ponytail" : policy.safe ? "safe" : "off";
  return <article className="panel policyPanel"><div className="panelHeader policyHeader"><div><p className="eyebrow">Output guardrails</p><h2>TokenPress policy</h2><small>Inherited by new gateway requests</small></div><span className="policyMode">{effective}</span></div><form action={updateTokenPolicy} className="policyForm"><input type="hidden" name="project_id" value={project.id} /><label className="switchRow"><span className="switchCopy"><strong>Safe compaction</strong><small>Lossless tool JSON and line cleanup</small></span><input type="checkbox" name="safe" defaultChecked={policy.safe} /><span className="switchTrack" aria-hidden="true"><i /></span></label><label className="switchRow"><span className="switchCopy"><strong>Caveman</strong><small>Concise output, full technical detail</small></span><input type="checkbox" name="caveman" defaultChecked={policy.caveman} /><span className="switchTrack" aria-hidden="true"><i /></span></label><label className="switchRow"><span className="switchCopy"><strong>Ponytail</strong><small>Smallest sufficient code change</small></span><input type="checkbox" name="ponytail" defaultChecked={policy.ponytail} /><span className="switchTrack" aria-hidden="true"><i /></span></label><div className="policyBottom"><span>{enabled}/3 policies active · output untouched</span><button type="submit">Apply to {project.name}</button></div></form></article>;
}
