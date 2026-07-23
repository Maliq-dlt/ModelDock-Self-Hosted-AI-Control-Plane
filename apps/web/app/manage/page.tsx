import { createModel, createProject, createProvider, createVirtualModel } from "../actions";
import { adminFetch } from "../../lib/api";

type Project = { id: string; name: string; slug: string };
type Provider = { id: string; name: string; provider_type: string };
type Model = { id: string; model_name: string; display_name: string | null };
type VirtualModel = { id: string };

function Field({ name, label, type = "text", placeholder, helper, required = true }: { name: string; label: string; type?: string; placeholder?: string; helper?: string; required?: boolean }) {
  return <label><span>{label}</span><input name={name} type={type} placeholder={placeholder} required={required} />{helper && <small>{helper}</small>}</label>;
}

function FormCard({ id, step, title, description, children, action, disabled, button }: { id: string; step: string; title: string; description: string; children: React.ReactNode; action: (form: FormData) => Promise<void>; disabled?: boolean; button: string }) {
  return <article className="formCard setupForm" id={id}><div className="formTitle"><span>{step}</span><div><h2>{title}</h2><p>{description}</p></div></div><form action={action}>{children}<button type="submit" disabled={disabled}>{disabled ? "Complete previous step" : button}</button></form></article>;
}

export default async function Manage() {
  const [projects, providers, models, routes] = await Promise.all([
    adminFetch<Project[]>("/api/projects").catch(() => []),
    adminFetch<Provider[]>("/api/providers").catch(() => []),
    adminFetch<Model[]>("/api/models").catch(() => []),
    adminFetch<VirtualModel[]>("/api/virtual-models").catch(() => []),
  ]);
  const progress = [projects.length, providers.length, models.length, routes.length].filter(Boolean).length;

  return <><header className="pageHeader setupHeader"><div><p className="eyebrow">Guided setup</p><h1>From zero to routed request.</h1><p>Use this page in order. Advanced fields stay optional.</p></div><div className="setupProgress"><strong>{progress}/4</strong><span>core steps complete</span><i><b style={{ width: `${progress * 25}%` }} /></i></div></header>
    <section className="setupNotice"><span>Tip</span><p>Local first? Choose Ollama, use <code>http://host.docker.internal:11434</code>, then register your installed model name.</p></section>
    <section className="formGrid guidedGrid">
      <FormCard id="project" step="01" title="Create workspace" description="One workspace groups routes, keys, budgets, and policies." action={createProject} button="Create workspace"><Field name="name" label="Workspace name" placeholder="My AI workspace" /><Field name="slug" label="Short ID" placeholder="my-ai-workspace" required={false} helper="Optional. Generated from name when empty." /><Field name="description" label="What is this for?" placeholder="Internal agents and coding tools" required={false} /></FormCard>

      <FormCard id="provider" step="02" title="Connect provider" description="Pick cloud API or a local runtime. Credentials are encrypted before storage." action={createProvider} button="Connect provider"><Field name="name" label="Connection name" placeholder="Local Ollama" /><label><span>Provider</span><select name="provider_type" defaultValue="ollama"><option value="ollama">Ollama - local and private</option><option value="openai">OpenAI - Chat Completions</option><option value="openai_responses">OpenAI - Responses API</option><option value="anthropic">Anthropic - Claude</option><option value="gemini">Google - Gemini</option><option value="groq">Groq - fast inference</option><option value="openai_compatible">OpenAI-compatible endpoint</option></select></label><Field name="base_url" label="Base URL" placeholder="http://host.docker.internal:11434" required={false} helper="Needed for Ollama and custom endpoints. Cloud providers can use defaults." /><Field name="api_key" label="API key" type="password" placeholder="Leave empty for Ollama" required={false} helper="Sent server-side and stored encrypted." /></FormCard>

      <FormCard id="model" step="03" title="Register model" description="Tell ModelDock which model lives behind the connection." action={createModel} button="Add model" disabled={!providers.length}><label><span>Provider connection</span><select name="provider_id" required>{providers.map((provider) => <option key={provider.id} value={provider.id}>{provider.name} / {provider.provider_type.replaceAll("_", " ")}</option>)}</select></label><Field name="model_name" label="Model ID" placeholder="llama3.2 or gpt-4.1-mini" helper="Use exact model name accepted by provider." /><Field name="display_name" label="Friendly name" placeholder="Fast coding model" required={false} /><Field name="context_window" label="Context window" type="number" placeholder="8192" required={false} /><details className="advancedFields"><summary>Optional pricing and tags</summary><Field name="capabilities" label="Capabilities" placeholder="chat,tools" required={false} /><Field name="tags" label="Tags" placeholder="coding,local,fast" required={false} /><div className="fieldPair"><Field name="input_cost_per_million" label="Input USD / 1M" type="number" placeholder="0" required={false} /><Field name="output_cost_per_million" label="Output USD / 1M" type="number" placeholder="0" required={false} /></div></details></FormCard>

      <FormCard id="route" step="04" title="Create route" description="Apps call one alias. ModelDock picks provider based on your strategy." action={createVirtualModel} button="Create route" disabled={!projects.length || !models.length}><label><span>Workspace</span><select name="project_id" required>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label><Field name="name" label="Route alias" placeholder="smart-router" helper="Your apps use this value as model name." /><label><span>Routing strategy</span><select name="strategy" defaultValue="priority"><option value="priority">Priority - primary then fallback</option><option value="cheapest">Cheapest - lowest configured price</option><option value="fastest">Fastest - lowest health-check latency</option><option value="weighted_score">Smart score - health, quality, speed, cost</option><option value="weighted_random">Traffic split - weighted random</option><option value="canary">Canary - safe percentage rollout</option></select><small>Priority is easiest and safest for first setup.</small></label><fieldset className="modelPicker"><legend>Models in this route</legend>{models.map((model, index) => <label key={model.id}><input type="checkbox" name="candidates" value={model.id} defaultChecked={index === 0} /><span><strong>{model.display_name ?? model.model_name}</strong><small>{model.model_name}</small></span></label>)}</fieldset><Field name="canary_percent" label="Canary traffic percent" type="number" placeholder="5" required={false} /></FormCard>
    </section>
  </>;
}
