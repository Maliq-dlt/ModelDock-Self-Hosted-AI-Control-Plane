import type { UsagePoint } from "../lib/api";

type Props = { points: UsagePoint[] };

function pathFor(points: UsagePoint[], key: "input_tokens" | "output_tokens", width: number, height: number, inset: number, max: number) {
  if (!points.length) return "";
  return points.map((point, index) => {
    const x = inset + (width - inset * 2) * (index / Math.max(1, points.length - 1));
    const y = height - inset - ((point[key] / max) * (height - inset * 2));
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export function ConsumptionChart({ points }: Props) {
  const width = 920;
  const height = 260;
  const inset = 22;
  const max = Math.max(1, ...points.flatMap((point) => [point.input_tokens, point.output_tokens]));
  const inputPath = pathFor(points, "input_tokens", width, height, inset, max);
  const outputPath = pathFor(points, "output_tokens", width, height, inset, max);
  const last = points.at(-1);

  return <article className="panel consumptionPanel"><div className="panelHeader chartHeader"><div><p className="eyebrow">Usage pulse</p><h2>Tokens over time</h2></div><div className="chartLegend"><span><i className="legendInput" />Input</span><span><i className="legendOutput" />Output</span></div></div><div className="chartCanvas">{points.length ? <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Input and output token consumption over time">{[0.25, 0.5, 0.75].map((level) => <line key={level} x1={inset} x2={width - inset} y1={height - inset - ((height - inset * 2) * level)} y2={height - inset - ((height - inset * 2) * level)} className="chartGridLine" />)}<path d={inputPath} className="chartLine chartInput" /><path d={outputPath} className="chartLine chartOutput" />{points.map((point, index) => { const x = inset + (width - inset * 2) * (index / Math.max(1, points.length - 1)); const y = height - inset - ((point.output_tokens / max) * (height - inset * 2)); return <circle key={point.date} cx={x} cy={y} r="3.5" className="chartDot" />; })}</svg> : <div className="chartEmpty"><span className="signalGlyph">--</span><strong>Waiting for first request</strong><small>Usage history appears after gateway traffic.</small></div>}</div><div className="chartFooter"><span>{points[0]?.date ?? "No data"}</span><strong>{last ? `${(last.input_tokens + last.output_tokens).toLocaleString()} tokens on latest day` : "No telemetry"}</strong><span>{last?.date ?? "No data"}</span></div></article>;
}
