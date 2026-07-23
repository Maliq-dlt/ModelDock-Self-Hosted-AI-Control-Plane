const gateway = "http://localhost:8080/v1";

export default function CliTools() {
  return <><header className="pageHeader"><div><p className="eyebrow">CLI tools</p><h1>First request in two minutes.</h1><p>Use any OpenAI-compatible client. Point it at ModelDock, then call your route alias.</p></div></header><section className="cliGrid"><article className="panel cliCard"><div className="cliCardTop"><span>PowerShell</span><b>Windows</b></div><pre>{`$headers = @{ Authorization = "Bearer md_live_..." }
$body = @{
  model = "smart-router"
  messages = @(@{ role = "user"; content = "Hello" })
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post \
  -Uri "${gateway}/chat/completions" \
  -Headers $headers \
  -ContentType "application/json" \
  -Body $body`}</pre></article><article className="panel cliCard"><div className="cliCardTop"><span>curl</span><b>Any shell</b></div><pre>{`curl ${gateway}/chat/completions \\
  -H "Authorization: Bearer md_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "smart-router",
    "messages": [{"role":"user","content":"Hello"}]
  }'`}</pre></article><article className="panel cliCard"><div className="cliCardTop"><span>Python SDK</span><b>OpenAI client</b></div><pre>{`from openai import OpenAI

client = OpenAI(
    api_key="md_live_...",
    base_url="${gateway}",
)
response = client.chat.completions.create(
    model="smart-router",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response.choices[0].message.content)`}</pre></article></section><section className="panel cliSteps"><p className="eyebrow">Before sending</p><div><span>01</span><strong>Create route</strong><small>Use alias like `smart-router`.</small></div><div><span>02</span><strong>Create key</strong><small>Copy from API Keys page.</small></div><div><span>03</span><strong>Send request</strong><small>Trace and usage appear automatically.</small></div></section></>;
}
