import { useEffect, useState } from "react";
import { api, ClassRoster, Profile, Trend } from "./api";
import { go, label, pct } from "./App";
import { LineChart } from "./charts";
import { ParentNote } from "./AiPanel";

// `examUuid` is the exam the teacher came from. The wrong-answer card shows
// that sitting; without it, the latest one.
export default function StudentPage({ studentId, examUuid }: { studentId: number; examUuid?: string }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [cls, setCls] = useState<ClassRoster | null>(null);
  const [error, setError] = useState("");
  const [shown, setShown] = useState<string | undefined>(examUuid);
  useEffect(() => setShown(examUuid), [studentId, examUuid]);
  useEffect(() => {
    setProfile(null); setTrend(null);
    api.profile(studentId).then(setProfile).catch((e) => setError(e.message));
    api.classes().then((cs) => {
      const found = cs.find((c) => c.students.some((s) => s.id === studentId)) ?? null;
      setCls(found);
      if (found) api.trend(found.id).then(setTrend).catch(() => setTrend(null));
    }).catch(() => undefined);
  }, [studentId]);
  if (error) return <div className="card empty">{error}</div>;
  if (!profile) return <div className="empty">載入中…</div>;

  const results = profile.results;
  const last = results[results.length - 1];
  const picked = results.find((r) => r.exam_uuid === shown) ?? last;
  const rate = (pair: [number, number]) => (pair[1] ? pair[0] / pair[1] : null);
  const sum = (k: "choice" | "mark") => results.reduce((a, r) => [a[0] + r[k][0], a[1] + r[k][1]] as [number, number], [0, 0] as [number, number]);
  const overall = results.length ? results.reduce((a, r) => a + r.correct / r.total, 0) / results.length : null;
  const classRate = trend?.exams.length ? trend.exams.reduce((a, e) => a + e.mean_rate, 0) / trend.exams.length : null;
  const labels = results.map((r) => r.unit ?? r.exam_date);
  const classByExam = new Map(trend?.exams.map((e) => [e.exam_uuid, e.mean_rate]) ?? []);
  const choice = rate(sum("choice")), mark = rate(sum("mark"));

  return (
    <>
      <div className="profile">
        <div className="big">{(profile.student_name ?? "?").slice(0, 1)}</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flex: 1 }}>
          <span className="crumb">
            <button type="button" className="crumblink" onClick={() => go(cls ? `/students/${cls.id}` : "/students")}>學生</button>
            {cls && <> / {cls.name}</>}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
            <h1>{profile.student_name}</h1>
            {cls && cls.students.length > 1 && (
              <select className="switch" aria-label="切換同班學生" value="" onChange={(e) => go(`/student/${e.target.value}${shown ? `/${shown}` : ""}`)}>
                <option value="" disabled>切換同班學生</option>
                {cls.students.filter((s) => s.id !== studentId).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            )}
          </div>
        </div>
        {overall !== null && classRate !== null && overall < classRate - 0.1 && <span className="pill bad" style={{ fontSize: 13, padding: "6px 12px" }}>平均比班上低 {Math.round((classRate - overall) * 100)}%</span>}
      </div>

      {results.length === 0 ? <div className="card empty">這位學生還沒有配對到任何考卷。</div> : (
        <>
          <div className="kpis">
            <div className="kpi"><span className="l">最近一次{last.unit ? `（${last.unit}）` : ""}</span><span className="v">{last.correct}<small>/ {last.total} 題</small></span><span className="s">{last.exam_date}</span></div>
            <div className="kpi"><span className="l">{results.length} 次平均</span><span className="v">{pct(overall)}</span><span className="s">班平均 {pct(classRate)}</span></div>
            <div className="kpi"><span className="l">選擇題</span><span className="v">{pct(choice)}</span>{choice !== null && choice < 0.5 ? <span className="s down">明顯偏弱</span> : <span className="s">累計</span>}</div>
            <div className="kpi"><span className="l">是非題</span><span className="v">{pct(mark)}</span><span className="s">亂猜 50%</span></div>
          </div>
          <div className="row2">
            <section className="card">
              <div className="title"><h2>各單元答對率</h2><span>和班平均比較</span></div>
              <LineChart onPoint={(i) => go(`/exam/${results[i].exam_uuid}`)}
                labels={labels}
                series={[
                  { label: "班平均", color: "var(--choice-l)", values: results.map((r) => classByExam.get(r.exam_uuid) ?? null), dashed: true, area: true },
                  { label: profile.student_name ?? "學生", color: "var(--bad)", values: results.map((r) => r.correct / r.total), emphasis: true },
                ]}
              />
            </section>
            <section className="card">
              <div className="title" style={{ alignItems: "center" }}>
                <h2>錯的題目</h2>
                {results.length > 1 ? (
                  <select className="switch" aria-label="選擇考試" style={{ maxWidth: 220 }} value={picked.exam_uuid} onChange={(e) => setShown(e.target.value)}>
                    {[...results].reverse().map((r) => (
                      <option key={r.exam_uuid} value={r.exam_uuid}>{r.unit ?? r.template_name} · {r.exam_date}{r === last ? "（最近一次）" : ""}</option>
                    ))}
                  </select>
                ) : <span>{picked.unit ?? picked.exam_date}</span>}
              </div>
              <span className="note">{picked.template_name} · 錯 {picked.wrong.length} 題 · 答對 {picked.correct}/{picked.total}</span>
              <div className="wrongrow" style={{ background: "none", paddingTop: 0 }}><span className="caption">題號</span><span className="caption">寫了</span><span className="caption">答案</span><span /></div>
              {picked.wrong.map((w) => (
                <div key={w.question_no} className="wrongrow">
                  <b>第 {w.question_no} 題</b><b className="w">{label(w.chosen)}</b><b className="k">{label(w.key)}</b>
                  <button type="button" className="linkbtn" style={{ marginLeft: 0, textAlign: "left" }} onClick={() => go(`/exam/${picked.exam_uuid}`)}>看全班</button>
                </div>
              ))}
              {picked.wrong.length === 0 && <span className="note">{picked.pending ? `沒有錯的題目，另有 ${picked.pending} 格待確認。` : "全對。"}</span>}
            </section>
          </div>
          <ParentNote studentId={studentId} />
        </>
      )}
    </>
  );
}
