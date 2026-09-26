// Every chart on the report pages, drawn with ECharts under one theme.
// Each one answers a hover with the numbers behind the mark and, where it
// makes sense, a click with a narrower view of the page.
import { useMemo, useState } from "react";
import { C, EChart, MONO, saveButton } from "./echart";

const tip = (rows: string) => `<div class="chart-tip">${rows}</div>`;
const pctText = (k: number, n: number) => (n ? `${Math.round((k / n) * 100)}%` : "—");

// ── 每題答對率 ───────────────────────────────────────────────────────────────

export type ItemBar = { q: number; type: "choice" | "mark"; correct: number; answered: number; flags: string[]; flagged: boolean };

const FLAG_SHORT: Record<string, string> = {
  unanimous_wrong: "全選同一個錯誤答案",
  popular_distractor: "多數人被同一個錯誤選項吸引",
  below_chance: "答對率低於亂猜",
  negative_discrimination: "高分組反而錯較多",
};

export function ItemBars({ items, selected, onSelect }: { items: ItemBar[]; selected: number | null; onSelect: (q: number) => void }) {
  const option = useMemo(() => {
    const hasMark = items.some((i) => i.type === "mark");
    return {
      toolbox: saveButton("每題答對率"),
      grid: { left: 40, right: 12, top: 30, bottom: 26 },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(45,90,61,0.06)" } },
        formatter: (ps: any[]) => {
          const it = items[ps[0].dataIndex];
          const flags = it.flags.filter((f) => f !== "guessable").map((f) => `<div class="f">${FLAG_SHORT[f] ?? f}</div>`).join("");
          return tip(`<div class="t">第 ${it.q} 題 · ${it.type === "choice" ? "選擇題" : "是非題"}</div>
            答對 <b>${it.correct}</b> / ${it.answered} 人（<b>${pctText(it.correct, it.answered)}</b>）${flags}
            <div style="color:#85918a;margin-top:2px">點一下看細節</div>`);
        },
      },
      xAxis: { type: "category", data: items.map((i) => i.q), axisLabel: { interval: 0, color: (_: unknown, i: number) => (items[i]?.flagged ? C.bad : C.ink3), fontWeight: 500 } },
      yAxis: { type: "value", max: 1, interval: 0.5, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` } },
      series: [{
        type: "bar", barCategoryGap: "22%",
        data: items.map((it) => ({
          value: it.answered ? it.correct / it.answered : 0,
          itemStyle: {
            color: it.flagged ? C.bad : it.type === "mark" ? C.markL : C.choice,
            opacity: selected === null || selected === it.q ? 1 : 0.42,
            borderRadius: [5, 5, 2, 2],
            borderColor: selected === it.q ? C.ink : "transparent", borderWidth: selected === it.q ? 2 : 0,
          },
        })),
        emphasis: { itemStyle: { opacity: 1 } },
        animationDelay: (i: number) => i * 18,
        markLine: hasMark ? {
          symbol: "none", silent: true,
          lineStyle: { color: "#c9c1ef", type: "dashed", width: 1 },
          label: { formatter: "亂猜基準 50%", position: "insideStartTop", color: C.mark, fontSize: 11, backgroundColor: "#ffffff", padding: [1, 4] },
          data: [{ yAxis: 0.5 }],
        } : undefined,
      }],
    };
  }, [items, selected]);
  return <EChart option={option} height={260} ariaLabel="每題答對率長條圖" onEvents={{ axisclick: (p) => items[p.dataIndex] && onSelect(items[p.dataIndex].q) }} />;
}

// ── 選項分布 ─────────────────────────────────────────────────────────────────

export function OptionBars({ counts, answerKey, lure, answered, small, selected, onSelect, label }: {
  counts: Record<string, number>; answerKey: string; lure: string | null; answered: number; small: boolean;
  selected: string | null; onSelect: (o: string) => void; label: (o: string) => string;
}) {
  const option = useMemo(() => {
    const opts = Object.keys(counts);
    const rev = [...opts].reverse();
    return {
      grid: { left: 34, right: 96, top: 4, bottom: 4 },
      tooltip: {
        trigger: "item",
        formatter: (p: any) => {
          const o = rev[p.dataIndex];
          const tag = o === answerKey ? "（正確答案）" : o === lure ? "（最多人選的錯誤選項）" : "";
          return tip(`<div class="t">選 ${label(o)}${tag}</div><b>${counts[o]}</b> 人${small ? "" : ` · <b>${pctText(counts[o], answered)}</b>`}<div style="color:#85918a">點一下看是哪些學生</div>`);
        },
      },
      xAxis: { type: "value", show: false, max: Math.max(1, ...Object.values(counts)) },
      yAxis: {
        type: "category", data: rev.map(label),
        axisLine: { show: false },
        axisLabel: { fontFamily: MONO, fontSize: 14, fontWeight: 600, color: (v: string) => (v === label(answerKey) ? C.brand : lure && v === label(lure) ? C.bad : C.ink2) },
      },
      series: [{
        type: "bar", barWidth: 20, showBackground: true, backgroundStyle: { color: "#f1f4f2", borderRadius: 6 },
        data: rev.map((o) => ({
          value: counts[o],
          itemStyle: {
            color: o === answerKey ? C.choice : o === lure ? C.bad : C.muted, borderRadius: 6,
            borderColor: selected === o ? C.ink : "transparent", borderWidth: selected === o ? 2 : 0,
          },
        })),
        label: { show: true, position: "right", distance: 8, fontFamily: MONO, color: C.ink2, fontSize: 12.5,
          formatter: (p: any) => `${p.value} 人${small ? "" : ` · ${pctText(p.value, answered)}`}` },
      }],
    };
  }, [counts, answerKey, lure, answered, small, selected, label]);
  const opts = Object.keys(counts);
  return <EChart option={option} height={Math.max(90, opts.length * 40)} ariaLabel="選項分布" onEvents={{ click: (p) => onSelect([...opts].reverse()[p.dataIndex]) }} />;
}

// ── 高分組 vs 低分組 ─────────────────────────────────────────────────────────

export function GroupBars({ options, high, low, highN, lowN, label }: {
  options: string[]; high: Record<string, number>; low: Record<string, number>; highN: number; lowN: number; label: (o: string) => string;
}) {
  const [asPct, setAsPct] = useState(true);
  const option = useMemo(() => {
    const val = (v: number, n: number) => (asPct ? (n ? v / n : 0) : v);
    return {
      grid: { left: 40, right: 8, top: 34, bottom: 22 },
      legend: { top: 0, left: 0, data: [`高分組 ${highN} 人`, `低分組 ${lowN} 人`] },
      tooltip: {
        trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(45,90,61,0.06)" } },
        formatter: (ps: any[]) => {
          const o = options[ps[0].dataIndex];
          return tip(`<div class="t">選 ${label(o)}</div>
            <span class="tip-dot" style="background:${C.brand}"></span>高分組 <b>${high[o] ?? 0}</b> / ${highN} 人（${pctText(high[o] ?? 0, highN)}）<br>
            <span class="tip-dot" style="background:${C.low}"></span>低分組 <b>${low[o] ?? 0}</b> / ${lowN} 人（${pctText(low[o] ?? 0, lowN)}）`);
        },
      },
      xAxis: { type: "category", data: options.map(label), axisLabel: { fontSize: 13, fontWeight: 600, color: C.ink2 } },
      yAxis: { type: "value", max: asPct ? 1 : undefined, minInterval: asPct ? undefined : 1, axisLabel: { formatter: (v: number) => (asPct ? `${Math.round(v * 100)}%` : `${v}`) } },
      series: [
        { name: `高分組 ${highN} 人`, type: "bar", barWidth: 14, itemStyle: { color: C.brand, borderRadius: [3, 3, 0, 0] }, data: options.map((o) => val(high[o] ?? 0, highN)) },
        { name: `低分組 ${lowN} 人`, type: "bar", barWidth: 14, itemStyle: { color: C.low, borderRadius: [3, 3, 0, 0] }, data: options.map((o) => val(low[o] ?? 0, lowN)) },
      ],
    };
  }, [options, high, low, highN, lowN, asPct, label]);
  return (
    <>
      <div className="seg" role="group" aria-label="顯示方式" style={{ alignSelf: "flex-start" }}>
        <button type="button" className={asPct ? "on" : ""} onClick={() => setAsPct(true)}>比例</button>
        <button type="button" className={!asPct ? "on" : ""} onClick={() => setAsPct(false)}>人數</button>
      </div>
      <EChart option={option} height={190} ariaLabel="高分組與低分組各選項比較" />
    </>
  );
}

// ── 答對題數分布 ─────────────────────────────────────────────────────────────

export function Histogram({ data, total, median, mean, selected, onSelect }: {
  data: { correct: number; papers: number }[]; total: number; median: number | null; mean: number | null;
  selected: number | null; onSelect: (correct: number | null) => void;
}) {
  const rows = useMemo(() => data.slice(Math.max(0, data.findIndex((d) => d.papers > 0) - 1)), [data]);
  const option = useMemo(() => ({
    toolbox: saveButton("答對題數分布"),
    grid: { left: 30, right: 10, top: 30, bottom: 26 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow", shadowStyle: { color: "rgba(45,90,61,0.06)" } },
      formatter: (ps: any[]) => { const d = rows[ps[0].dataIndex]; return tip(`答對 <b>${d.correct}</b> 題：<b>${d.papers}</b> 份${d.papers ? '<div style="color:#85918a">點一下只看這些學生</div>' : ""}`); },
    },
    xAxis: { type: "category", data: rows.map((d) => String(d.correct)), axisLabel: { interval: (i: number) => rows[i].correct % 5 === 0 || rows[i].correct === total } },
    yAxis: { type: "value", minInterval: 1 },
    series: [{
      type: "bar", barCategoryGap: "12%",
      data: rows.map((d) => ({
        value: d.papers,
        itemStyle: { color: selected === d.correct ? C.brand : C.choiceL, borderRadius: [3, 3, 0, 0], opacity: selected === null || selected === d.correct ? 1 : 0.5 },
      })),
      label: { show: true, position: "top", fontFamily: MONO, fontSize: 10, color: C.ink3, formatter: (p: any) => (p.value ? p.value : "") },
      markLine: {
        symbol: "none", silent: true, label: { position: "end", fontSize: 11, formatter: (p: any) => p.name },
        data: [
          ...(median !== null ? [{ name: `中位數 ${median}`, xAxis: String(Math.round(median)), lineStyle: { color: C.brand, type: "solid", width: 1.5 }, label: { color: C.brand } }] : []),
          ...(mean !== null ? [{ name: `平均 ${mean}`, xAxis: String(Math.round(mean)), lineStyle: { color: C.mark, type: "dashed", width: 1.2 }, label: { color: C.mark, position: "insideEndTop" } }] : []),
        ],
      },
    }],
  }), [rows, total, median, mean, selected]);
  return <EChart option={option} height={210} ariaLabel="答對題數分布" onEvents={{ axisclick: (p) => { const d = rows[p.dataIndex]; if (d?.papers) onSelect(selected === d.correct ? null : d.correct); } }} />;
}

// ── 趨勢折線 ─────────────────────────────────────────────────────────────────

export type Series = { label: string; color: string; values: (number | null)[]; dashed?: boolean; area?: boolean; emphasis?: boolean };

export function LineChart({ labels, series, height = 250, onPoint, name = "各單元答對率" }: {
  labels: string[]; series: Series[]; height?: number; onPoint?: (index: number) => void; name?: string;
}) {
  const clickable = !!onPoint;
  const option = useMemo(() => ({
    toolbox: saveButton(name),
    grid: { left: 44, right: 26, top: 46, bottom: 28 },
    legend: { top: 0, left: 0, data: series.map((s) => s.label) },
    tooltip: {
      trigger: "axis", axisPointer: { type: "line", lineStyle: { color: C.line, width: 1 } },
      formatter: (ps: any[]) => tip(`<div class="t">${labels[ps[0].dataIndex]}</div>` + ps.map((p) => `<span class="tip-dot" style="background:${p.color}"></span>${p.seriesName} <b>${p.value === null || p.value === undefined ? "—" : `${Math.round(p.value * 100)}%`}</b>`).join("<br>") + (clickable ? '<div style="color:#85918a;margin-top:2px">點一下打開這次考試</div>' : "")),
    },
    xAxis: { type: "category", data: labels, boundaryGap: labels.length < 3, axisLabel: { color: C.ink2, fontSize: 12 } },
    yAxis: { type: "value", min: 0, max: 1, interval: 0.25, axisLabel: { formatter: (v: number) => `${Math.round(v * 100)}%` } },
    series: series.map((s) => ({
      name: s.label, type: "line", data: s.values, connectNulls: true, smooth: 0.25,
      symbol: "circle", symbolSize: s.emphasis ? 9 : 6, showSymbol: true,
      lineStyle: { color: s.color, width: s.emphasis ? 3 : 2, type: s.dashed ? "dashed" : "solid" },
      itemStyle: { color: s.color },
      areaStyle: s.area ? { color: "rgba(156,201,174,0.18)" } : undefined,
      label: s.emphasis ? { show: true, position: "top", fontFamily: MONO, fontWeight: 600, color: s.color, formatter: (p: any) => `${Math.round(p.value * 100)}%` } : undefined,
      emphasis: { focus: "series" },
      z: s.emphasis ? 3 : 2,
    })),
  }), [labels, series, name, clickable]);
  return <EChart option={option} height={height} ariaLabel={name} onEvents={{ click: (p) => onPoint?.(p.dataIndex) }} />;
}

// ── 卡片裡的小趨勢線（純 SVG，沒有互動需要） ───────────────────────────────

export function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const W = 140, H = 44, min = Math.min(...values) - 0.05, max = Math.max(...values) + 0.05;
  const pts = values.map((v, i) => [4 + (i * (W - 8)) / (values.length - 1), H - 6 - ((v - min) / (max - min)) * (H - 12)]);
  const last = pts[pts.length - 1];
  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} aria-hidden="true">
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke={C.choice} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last[0]} cy={last[1]} r="4" fill={C.brand} />
    </svg>
  );
}
