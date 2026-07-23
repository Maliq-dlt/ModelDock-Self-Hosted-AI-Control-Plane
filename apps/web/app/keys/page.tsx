import { ApiKeyForm } from "../../components/api-key-form";
import { adminFetch, ApiKey } from "../../lib/api";

type Project = { id: string; name: string };

export default async function Keys() {
  const [keys, projects] = await Promise.all([adminFetch<ApiKey[]>("/api/api-keys").catch(() => []), adminFetch<Project[]>("/api/projects").catch(() => [])]);
  const projectNames = new Map(projects.map((project) => [project.id, project.name]));
  return <><header className="pageHeader"><div><p className="eyebrow">Access control</p><h1>Keys for your apps.</h1><p>Create a project key, copy it once, and keep it out of frontend code.</p></div></header><section className="keyLayout"><article className="panel keyCreatePanel"><div className="panelHeader"><div><p className="eyebrow">New credential</p><h2>Create API key</h2></div><span className="secureBadge">server-side</span></div><ApiKeyForm projects={projects} /></article><article className="panel listPanel"><div className="panelHeader"><div><p className="eyebrow">Issued credentials</p><h2>Key inventory</h2></div><span className="microBadge">{keys.length} keys</span></div>{keys.length ? <div className="keyList">{keys.map((key) => <div className="keyRow" key={key.id}><div><strong>{key.name}</strong><small>{projectNames.get(key.project_id) ?? "Unknown workspace"} / {key.key_prefix}...</small></div><span className={`status ${key.status === "active" ? "success" : "error"}`}>{key.status}</span><div><small>{key.rate_limit_rpm} RPM / {key.concurrent_limit} concurrent</small><small>{key.last_used_at ? `Used ${new Date(key.last_used_at).toLocaleString()}` : "Not used yet"}</small></div></div>)}</div> : <div className="emptyInner">No keys issued yet.</div>}</article></section><section className="securityNote"><span>Key rule</span><p>Use `md_live_*` for production and `md_test_*` for development. Revoke exposed keys from API or admin tooling.</p></section></>;
}
