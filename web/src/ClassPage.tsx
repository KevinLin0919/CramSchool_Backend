import { useEffect, useState } from "react";
import { api, Trend } from "./api";
import { go, pct } from "./App";
import { LineChart } from "./charts";

export default function ClassPage({ classId }: { classId: number }) {
  const [trend, setTrend] = useState<Trend | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { setTrend(null); api.trend(classId).then(setTrend).catch((e) => setError(e.message)); }, [classId]);
  if (error) return <div className="card empty">{error}</div>;
  if (!trend) return <div className="empty">載入中…</div>;
  const labels = trend.exams.map((e) => e.unit ?? e.exam_date);
  const lastTwo = trend.exams.slice(-2);
  const change = lastTwo.length === 2 ? lastTwo[1].mean_rate - lastTwo[0].mean_rate : null;

  return (
    <>
      <div className="head"><div><span className="crumb">單元趨勢</span><h1>各單元表現</h1><span style={{ color: "var(--ink2)" }}>同一個班在各單元的答對率。</span></div></div>
      <div className="kpis">
        <div className="kpi"><span className="l">考試次數</span><span className="v">{trend.exams.length}</span></div>
        <div className="kpi"><span className="l">最近一次</span><span className="v">{pct(trend.exams[trend.exams.length - 1]?.mean_rate)}</span>{change !== null && <span className={`s ${change < 0 ? "down" : "up"}`}>{change < 0 ? "▼" : "▲"} {Math.abs(Math.round(change * 100))}%　比上一次</span>}</div>
        <div className="kpi"><span className="l">學生</span><span className="v">{trend.students.length}<small>人</small></span></div>
      </div>
      <section className="card">
        <div className="title"><h2>全班答對率</h2><span>整體、選擇題、是非題</span></div>
        <LineChart labels={labels} series={[
          { label: "是非題", color: "var(--mark)", values: trend.exams.map((e) => e.mark_rate) },
          { label: "選擇題", color: "var(--choice)", values: trend.exams.map((e) => e.choice_rate) },
          { label: "整體", color: "#16211b", values: trend.exams.map((e) => e.mean_rate), emphasis: true },
        ]} height={240} />
        <div className="legend">
          <span><i className="line" style={{ background: "#16211b" }} />整體</span>
          <span><i className="line" style={{ background: "var(--choice)" }} />選擇題</span>
          <span><i className="line" style={{ background: "var(--mark)" }} />是非題</span>
        </div>
      </section>
      <section className="card">
        <div className="title"><h2>學生</h2><span>各單元答對率</span></div>
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: `minmax(0,1.2fr) repeat(${trend.exams.length}, minmax(0,1fr))` }}><span>學生</span>{labels.map((l, i) => <span key={i} className="n">{l}</span>)}</div>
          {trend.students.map((s) => (
            <button key={s.student_id} type="button" className="tr" style={{ gridTemplateColumns: `minmax(0,1.2fr) repeat(${trend.exams.length}, minmax(0,1fr))`, padding: "9px 12px" }} onClick={() => go(`/student/${s.student_id}`)}>
              <span>{s.student_name}</span>
              {trend.exams.map((e) => {
                const r = s.results.find((x) => x.exam_uuid === e.exam_uuid)?.rate;
                return <span key={e.exam_uuid} className="n" style={{ color: r !== undefined && r < 0.5 ? "var(--bad-d)" : undefined, fontWeight: r !== undefined && r < 0.5 ? 700 : 400 }}>{pct(r)}</span>;
              })}
            </button>
          ))}
        </div>
      </section>
    </>
  );
}
