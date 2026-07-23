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

export default async function TraceDetail({
  params,
}: {
  params: Promise<{ traceId: string }>;
}) {
  const { traceId } = await params;
  const trace = await adminFetch<Detail>(`/api/traces/${traceId}`);

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
