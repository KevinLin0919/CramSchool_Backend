// Charts drawn to one scale each, so every label names a value the chart
// reaches. Plain SVG and flex boxes: these are the only shapes the pages need.

export type ItemBar = { q: number; type: "choice" | "mark"; rate: number; flagged: boolean };

export function ItemBars({ items, selected, onSelect }: { items: ItemBar[]; selected: number | null; onSelect: (q: number) => void }) {
  const H = 206;
  const showBase = items.some((i) => i.type === "mark");
  return (
    <>
      <div className="bars">
        {showBase && <div className="base" style={{ bottom: H * 0.5 }}><span>亂猜基準 50%</span></div>}
        {items.map((it) => (
          <button
            key={it.q}
            type="button"
            aria-label={`第 ${it.q} 題 答對 ${Math.round(it.rate * 100)}%`}
            className={`col1 ${selected === it.q ? "sel" : ""} ${selected !== null && selected !== it.q ? "dim" : ""}`}
            onClick={() => onSelect(it.q)}
          >
            {it.flagged && <b>!</b>}
            <i style={{ height: Math.max(3, it.rate * H), background: it.flagged ? "var(--bad)" : it.type === "mark" ? "var(--mark-l)" : "var(--choice)" }} />
          </button>
        ))}
      </div>
      <div className="axis">
        {items.map((it) => <span key={it.q} className={it.flagged ? "flag" : ""}>{it.q}</span>)}
      </div>
    </>
  );
}

export function Histogram({ data, total, mark }: { data: { correct: number; papers: number }[]; total: number; mark?: number | null }) {
  const trimmed = data.filter((d, i) => d.papers > 0 || data.slice(0, i).some((x) => x.papers > 0));
  const first = trimmed[0]?.correct ?? 0;
  const rows = data.filter((d) => d.correct >= first);
  const max = Math.max(1, ...rows.map((d) => d.papers));
  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 120, borderBottom: "1px solid #dfe5e1" }}>
        {rows.map((d) => (
          <div key={d.correct} title={`${d.correct} 題：${d.papers} 份`} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-end", height: "100%", gap: 2 }}>
            {d.papers > 0 && <span style={{ fontSize: 10, color: "var(--ink3)" }}>{d.papers}</span>}
            <div style={{ width: "100%", height: (d.papers / max) * 100, background: mark !== undefined && mark !== null && d.correct === Math.round(mark) ? "var(--brand)" : "var(--choice-l)", borderRadius: "3px 3px 0 0" }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--ink3)" }}>
        <span>{first} 題</span><span>{total} 題</span>
      </div>
    </>
  );
}

export type Series = { label: string; color: string; values: (number | null)[]; dashed?: boolean; area?: boolean; emphasis?: boolean };

export function LineChart({ labels, series, height = 220 }: { labels: string[]; series: Series[]; height?: number }) {
  const W = 560, H = height, left = 44, right = 20, top = 18, bottom = 34;
  const x = (i: number) => labels.length <= 1 ? (left + W - right) / 2 : left + 30 + (i * (W - left - right - 60)) / (labels.length - 1);
  const y = (v: number) => top + (1 - v) * (H - top - bottom);
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="各單元答對率" style={{ display: "block" }}>
      {[1, 0.5, 0].map((r) => (
        <g key={r}>
          <line x1={left} x2={W - right} y1={y(r)} y2={y(r)} stroke={r === 0 ? "#dfe5e1" : "#eef1ef"} />
          <text x={left - 8} y={y(r) + 4} textAnchor="end" fontSize="11" fill="#85918a">{Math.round(r * 100)}%</text>
        </g>
      ))}
      {series.map((s) => {
        const pts = s.values.map((v, i) => (v === null ? null : [x(i), y(v)] as const)).filter(Boolean) as (readonly [number, number])[];
        if (!pts.length) return null;
        const path = pts.map((p) => p.join(",")).join(" ");
        return (
          <g key={s.label}>
            {s.area && <polygon points={`${path} ${pts[pts.length - 1][0]},${y(0)} ${pts[0][0]},${y(0)}`} fill="#e4efe8" opacity="0.6" />}
            <polyline points={path} fill="none" stroke={s.color} strokeWidth={s.emphasis ? 3 : 2.5} strokeDasharray={s.dashed ? "6 5" : undefined} strokeLinecap="round" strokeLinejoin="round" />
            {s.emphasis && pts.map(([px, py], i) => (
              <g key={i}>
                <circle cx={px} cy={py} r={i === pts.length - 1 ? 5.5 : 4.5} fill={s.color} />
                <text x={px} y={py - 11} textAnchor="middle" fontSize="12" fontWeight="700" fill={s.color}>{Math.round((s.values[i] ?? 0) * 100)}%</text>
              </g>
            ))}
          </g>
        );
      })}
      {labels.map((l, i) => <text key={l + i} x={x(i)} y={H - 10} textAnchor="middle" fontSize="12" fill="#4b5a51">{l}</text>)}
    </svg>
  );
}

export function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const W = 140, H = 44, min = Math.min(...values) - 0.05, max = Math.max(...values) + 0.05;
  const pts = values.map((v, i) => [4 + (i * (W - 8)) / (values.length - 1), H - 6 - ((v - min) / (max - min)) * (H - 12)]);
  const last = pts[pts.length - 1];
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="var(--choice)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="4" fill="var(--brand)" />
    </svg>
  );
}

export function GroupBars({ options, high, low, label }: { options: string[]; high: Record<string, number>; low: Record<string, number>; label: (o: string) => string }) {
  const max = Math.max(1, ...options.map((o) => Math.max(high[o] ?? 0, low[o] ?? 0)));
  return (
    <>
      <div style={{ display: "flex", alignItems: "flex-end", gap: 14, height: 120, borderBottom: "1px solid #dfe5e1", padding: "0 6px" }}>
        {options.map((o) => (
          <div key={o} style={{ flex: 1, display: "flex", justifyContent: "center", alignItems: "flex-end", gap: 3, height: "100%" }}>
            <div title={`高分組 ${high[o] ?? 0}`} style={{ width: 14, height: ((high[o] ?? 0) / max) * 100, background: "var(--brand)", borderRadius: "3px 3px 0 0" }} />
            <div title={`低分組 ${low[o] ?? 0}`} style={{ width: 14, height: ((low[o] ?? 0) / max) * 100, background: "#b7c9bd", borderRadius: "3px 3px 0 0" }} />
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 14, padding: "0 6px" }}>
        {options.map((o) => <span key={o} style={{ flex: 1, textAlign: "center", fontSize: 12, fontWeight: 700, color: "var(--ink2)" }}>{label(o)}</span>)}
      </div>
    </>
  );
}
