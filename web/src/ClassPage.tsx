import { useEffect, useState } from "react";
import { api, Trend } from "./api";
import { go } from "./App";
import { RateColumns } from "./charts";

export default function ClassPage({ classId }: { classId: number }) {
  const [trend, setTrend] = useState<Trend | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setTrend(null);
    api.trend(classId).then(setTrend).catch((e) => setError(e.message));
  }, [classId]);
  if (error) return <div className="card empty">{error}</div>;
  if (!trend) return <div className="empty">載入中…</div>;
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
  const units = trend.exams.map((e) => e.unit ?? e.template_name);

  return (
    <>
      <div className="crumb"><a href="#/exams">考試</a> › 班級</div>
      <h1>各單元表現</h1>
      <p className="sub">同一個班在各單元的答對率。</p>
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>全班答對率</h2>
        <RateColumns rows={trend.exams.map((e) => ({ label: e.unit ?? e.exam_date, values: [e.mean_rate, e.choice_rate, e.mark_rate] }))} />
        <div className="legend">
          <span><i style={{ background: "var(--brand)" }} />整體</span>
          <span><i style={{ background: "var(--brand-m)" }} />選擇題</span>
          <span><i style={{ background: "var(--mark)" }} />是非題</span>
        </div>
      </div>
      <div className="card">
        <h2>學生 <span>各單元答對率</span></h2>
        <table>
          <thead><tr><th>學生</th>{units.map((u) => <th key={u} className="n">{u}</th>)}</tr></thead>
          <tbody>
            {trend.students.map((s) => (
              <tr key={s.student_id} className="link" onClick={() => go(`/student/${s.student_id}`)}>
                <td>{s.student_name ?? "—"}</td>
                {trend.exams.map((e) => (
                  <td key={e.exam_uuid} className="n">{pct(s.results.find((r) => r.exam_uuid === e.exam_uuid)?.rate)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
