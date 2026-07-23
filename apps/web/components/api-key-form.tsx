"use client";

import { useActionState, useState } from "react";
import { createApiKey, type ApiKeyState } from "../app/actions";

type Project = { id: string; name: string };

const initialState: ApiKeyState = { rawKey: "", error: "" };

export function ApiKeyForm({ projects }: { projects: Project[] }) {
  const [state, formAction, pending] = useActionState(createApiKey, initialState);
  const [copied, setCopied] = useState(false);

  async function copyKey() {
    if (!state.rawKey) return;
    await navigator.clipboard.writeText(state.rawKey);
    setCopied(true);
  }

  return <div className="keyFormWrap"><form action={formAction} className="keyForm"><label><span>Workspace</span><select name="project_id" required>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><label><span>Key name</span><input name="name" placeholder="Local app" required /></label><div className="fieldPair"><label><span>Environment</span><select name="environment" defaultValue="live"><option value="live">Live</option><option value="test">Test</option></select></label><label><span>Requests per minute</span><input name="rate_limit_rpm" type="number" min="0" defaultValue="60" /></label></div><div className="fieldPair"><label><span>Monthly token limit</span><input name="token_limit_monthly" type="number" min="1" placeholder="No limit" /></label><label><span>Concurrent requests</span><input name="concurrent_limit" type="number" min="1" defaultValue="4" /></label></div><button type="submit" disabled={pending || !projects.length}>{pending ? "Creating..." : "Create API key"}</button></form>{state.error && <p className="errorText formError">{state.error}</p>}{state.rawKey && <div className="rawKeyNotice"><div><strong>Copy this key now</strong><small>ModelDock will not show it again.</small></div><code>{state.rawKey}</code><button type="button" onClick={copyKey}>{copied ? "Copied" : "Copy key"}</button></div>}</div>;
}
