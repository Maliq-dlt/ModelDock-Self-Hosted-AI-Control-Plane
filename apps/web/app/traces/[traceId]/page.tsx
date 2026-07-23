import { adminFetch } from "../../../lib/api";

type Attempt = {
  attempt_number: number;
  status: string;
  provider_id: string;
  model_id: string;
  latency_ms: number | null;
  error_type: string | null;
  error_message: string | null;
};

type Detail = {
  trace_id: string;
  status: string;
  virtual_model: string;
  latency_ms: number | null;
  usage: { total_tokens: number; estimated_cost: number };
  metadata: Record<string, unknown>;
  attempts: Attempt[];
};

type Replay = {
  trace_id: string;
  status: "ready" | "unavailable";
  changed?: boolean;
  error?: unknown;
  original: { provider?: string | null; model?: string | null };
  current?: Array<{ provider: string; model: string }>;
  decision?: Record<string, unknown>;
};

export default async function TraceDetail({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  const [trace, replay] = await Promise.all([
    adminFetch<Detail>(`/api/traces/${traceId}`),
    adminFetch<Replay>(`/api/traces/${traceId}/replay`).catch(() => null),
  ]);
  const current = replay?.current?.[0];
  const reason = typeof replay?.decision?.reason === "string" ? replay.decision.reason : "Route cannot be recalculated.";

  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Trace detail</p>
          <h1 className="mono">{trace.trace_id}</h1>
          <p>
            {trace.virtual_model} / {trace.latency_ms ? `${Math.round(trace.latency_ms)} ms` : "pending"} / ${trace.usage.estimated_cost.toFixed(5)}
          </p>
        </div>
        <span className={`status ${trace.status}`}>{trace.status}</span>
      </header>
      <section className="decisionStrip replayStrip">
        <div className="receiptStamp"><span>DR</span><small>Decision replay</small></div>
        <div>
          <p className="eyebrow">Current routing result</p>
          <h2>{replay?.status === "ready" ? reason : "Replay unavailable"}</h2>
          <p>{current ? `${current.provider} / ${current.model}` : "Original routing context no longer resolves."}</p>
        </div>
        <div className="receiptFacts">
          <span>Original<strong>{replay?.original?.provider ?? "—"}</strong></span>
          <span>Result<strong>{replay?.changed ? "changed" : "stable"}</strong></span>
          <span>Provider calls<strong>zero</strong></span>
        </div>
      </section>
      <section className="timeline">
        {trace.attempts.map((attempt) => (
          <article key={attempt.attempt_number}>
            <div className="timelineDot" />
            <div>
              <span>Attempt {attempt.attempt_number}</span>
              <h2>{attempt.status === "success" ? "Provider completed request" : attempt.error_type ?? "Provider attempt"}</h2>
              <p className="mono">provider {attempt.provider_id} / model {attempt.model_id}</p>
              {attempt.error_message && <p className="errorText">{attempt.error_message}</p>}
            </div>
            <strong>{attempt.latency_ms ? `${Math.round(attempt.latency_ms)} ms` : "-"}</strong>
          </article>
        ))}
      </section>
      <section className="panel jsonPanel">
        <p className="eyebrow">Routing decision</p>
        <pre>{JSON.stringify(trace.metadata, null, 2)}</pre>
      </section>
    </>
  );
}