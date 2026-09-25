// Small SVG charts drawn to one scale each, so every label names a value the
// chart actually reaches. No charting library: these are the only three
// shapes the reports need.

export function Histogram({ data, total }: { data: { correct: number; papers: number }[]; total: number }) {
  const max = Math.max(1, ...data.map((d) => d.papers));
  const w = 560, h = 150, pad = 22;
  const bw = (w - pad * 2) / Math.max(1, data.length);
  return (
    <svg viewBox={`0 0 ${w} ${h + 22}`} width="100%" role="img" aria-label="答對題數分布">
      {data.map((d, i) => {
        const bh = ((h - 16) * d.papers) / max;
        return (
          <g key={d.correct}>
            <rect x={pad + i * bw + 1} y={h - bh} width={Math.max(1, bw - 2)} height={bh} rx={2} fill="var(--brand-m)" />
            {d.papers > 0 && (
              <text x={pad + i * bw + bw / 2} y={h - bh - 3} textAnchor="middle">{d.papers}</text>
            )}
          </g>
        );
      })}
      <line x1={pad} x2={w - pad} y1={h} y2={h} stroke="var(--line)" />
      {data.map((d, i) =>
        d.correct % 5 === 0 || d.correct === total ? (
          <text key={d.correct} x={pad + i * bw + bw / 2} y={h + 14} textAnchor="middle">{d.correct}</text>
        ) : null,
      )}
    </svg>
  );
}

export type ItemBar = { q: number; type: "choice" | "mark"; correct: number; answered: number; flagged: boolean };

export function ItemBars({ items, selected, onSelect }: { items: ItemBar[]; selected: number | null; onSelect: (q: number) => void }) {
  const w = 560, h = 150, pad = 18;
  const bw = (w - pad * 2) / Math.max(1, items.length);
  return (
    <svg viewBox={`0 0 ${w} ${h + 22}`} width="100%" role="img" aria-label="每題答對比例">
      {[0.5, 1].map((r) => (
        <g key={r}>
          <line x1={pad} x2={w - pad} y1={h - (h - 10) * r} y2={h - (h - 10) * r} stroke="var(--line2)" strokeDasharray={r === 0.5 ? "3 3" : undefined} />
        </g>
      ))}
      {items.map((it, i) => {
        const rate = it.answered ? it.correct / it.answered : 0;
        const bh = Math.max(2, (h - 10) * rate);
        const fill = it.flagged ? "var(--bad)" : it.type === "mark" ? "var(--mark)" : "var(--brand-m)";
        return (
          <g key={it.q} onClick={() => onSelect(it.q)} style={{ cursor: "pointer" }}>
            <rect x={pad + i * bw} y={0} width={bw} height={h} fill="transparent" />
            <rect
              x={pad + i * bw + 1.5}
              y={h - bh}
              width={Math.max(1, bw - 3)}
              height={bh}
              rx={2}
              fill={fill}
              opacity={selected === null || selected === it.q ? 1 : 0.45}
              stroke={selected === it.q ? "var(--ink)" : "none"}
              strokeWidth={1.5}
            />
          </g>
        );
      })}
      <line x1={pad} x2={w - pad} y1={h} y2={h} stroke="var(--line)" />
      {items.map((it, i) =>
        i === 0 || it.q % 5 === 0 ? (
          <text key={it.q} x={pad + i * bw + bw / 2} y={h + 14} textAnchor="middle">{it.q}</text>
        ) : null,
      )}
    </svg>
  );
}

export function RateColumns({ rows }: { rows: { label: string; values: (number | null)[] }[] }) {
  const colors = ["var(--brand)", "var(--brand-m)", "var(--mark)"];
  const w = 560, h = 150, pad = 26;
  const gw = (w - pad * 2) / Math.max(1, rows.length);
  const bw = Math.min(26, (gw - 16) / 3);
  return (
    <svg viewBox={`0 0 ${w} ${h + 24}`} width="100%" role="img" aria-label="各單元答對率">
      {[0, 0.5, 1].map((r) => (
        <g key={r}>
          <line x1={pad} x2={w - pad} y1={h - (h - 12) * r} y2={h - (h - 12) * r} stroke="var(--line2)" />
          <text x={pad - 4} y={h - (h - 12) * r + 3} textAnchor="end">{Math.round(r * 100)}%</text>
        </g>
      ))}
      {rows.map((row, i) => (
        <g key={row.label}>
          {row.values.map((v, j) =>
            v === null ? null : (
              <rect key={j} x={pad + i * gw + gw / 2 - (bw * 3) / 2 + j * bw + 1} y={h - (h - 12) * v} width={bw - 2} height={(h - 12) * v} rx={2} fill={colors[j]} />
            ),
          )}
          <text x={pad + i * gw + gw / 2} y={h + 15} textAnchor="middle">{row.label}</text>
        </g>
      ))}
    </svg>
  );
}
