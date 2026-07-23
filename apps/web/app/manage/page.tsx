import { createApiKey, createBudget, createModel, createProject, createProvider, createVirtualModel } from "../actions";
import { adminFetch } from "../../lib/api";

type Project = { id: string; name: string; slug: string };
type Provider = { id: string; name: string; provider_type: string };
type Model = { id: string; model_name: string };

function Field({ name, label, type = "text", placeholder }: { name: string; label: string; type?: string; placeholder?: string }) {
  const optional = new Set(["description", "display_name", "base_url", "credentials", "tags", "pricing"]);
  return <label><span>{label}</span><input name={name} type={type} placeholder={placeholder} required={!optional.has(name)} /></label>;
}

function FormCard({ title, children, action }: { title: string; children: React.ReactNode; action: (form: FormData) => Promise<void> }) {
  return <article className="formCard"><h2>{title}</h2><form action={action}>{children}<button type="submit">Create</button></form></article>;
}

export default async function Manage() {
  const [projects, providers, models] = await Promise.all([
    adminFetch<Project[]>("/api/projects").catch(() => []),
    adminFetch<Provider[]>("/api/providers").catch(() => []),
    adminFetch<Model[]>("/api/models").catch(() => []),
  ]);
  return <><header className="pageHeader"><div><p className="eyebrow">Administration</p><h1>Configure ModelDock.</h1><p>Management calls stay server-side. Provider credentials never enter browser JavaScript.</p></div></header><section className="formGrid">
    <FormCard title="New project" action={createProject}><Field name="name" label="Name" /><Field name="slug" label="Slug" /><Field name="description" label="Description" /></FormCard>
    <FormCard title="New provider" action={createProvider}><Field name="name" label="Name" /><label><span>Type</span><select name="provider_type" defaultValue="ollama"><option value="openai">OpenAI</option><option value="gemini">Gemini</option><option value="groq">Groq</option><option value="ollama">Ollama</option><option value="openai_compatible">OpenAI compatible</option></select></label><Field name="base_url" label="Base URL" placeholder="https://..." /><label><span>Encrypted credentials JSON</span><textarea name="credentials" placeholder='{"api_key":"..."}' /></label></FormCard>
    <FormCard title="Register model" action={createModel}><label><span>Provider</span><select name="provider_id" required>{providers.map(provider => <option key={provider.id} value={provider.id}>{provider.name}</option>)}</select></label><Field name="model_name" label="Model name" /><Field name="display_name" label="Display name" /><Field name="context_window" label="Context window" type="number" placeholder="8192" /><Field name="capabilities" label="Capabilities" placeholder="chat,tools" /><Field name="tags" label="Tags" placeholder="coding,local" /><Field name="pricing" label="Pricing JSON" placeholder='{"input_cost_per_million":1}' /></FormCard>
    <FormCard title="Virtual model" action={createVirtualModel}><label><span>Project</span><select name="project_id" required>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><Field name="name" label="Alias" /><label><span>Strategy</span><select name="strategy" defaultValue="priority"><option value="priority">Priority</option><option value="cheapest">Cheapest</option></select></label><Field name="candidates" label="Model IDs, comma separated" placeholder={models.map(model => model.id).join(",")} /></FormCard>
    <FormCard title="Project API key" action={createApiKey}><label><span>Project</span><select name="project_id" required>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><Field name="name" label="Key name" /><label><span>Environment</span><select name="environment" defaultValue="live"><option value="live">Live</option><option value="test">Test</option></select></label><p className="formHint">For secure raw-key capture, use API docs. Raw key is returned once.</p></FormCard>
    <FormCard title="Monthly budget" action={createBudget}><label><span>Project</span><select name="scope_id" required>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><Field name="limit_amount" label="Limit USD" type="number" placeholder="100" /><Field name="warning_threshold" label="Warning ratio" type="number" placeholder="0.8" /><label><span>At limit</span><select name="action_at_limit" defaultValue="block"><option value="block">Block</option><option value="warn">Warn</option></select></label></FormCard>
  </section></>;
}
