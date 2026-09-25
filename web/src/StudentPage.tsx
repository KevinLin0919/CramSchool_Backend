import { useEffect, useState } from "react";
import { api, Profile } from "./api";
import { go } from "./App";

export default function StudentPage({ studentId }: { studentId: number }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.profile(studentId).then(setProfile).catch((e) => setError(e.message));
  }, [studentId]);
  if (error) return <div className="card empty">{error}</div>;
  if (!profile) return <div className="empty">載入中…</div>;
  const label = (o: string) => (o === "O" ? "○" : o === "X" ? "✕" : o === "__blank__" ? "空白" : o);
  const rate = (pair: [number, number]) => (pair[1] ? `${Math.round((pair[0] / pair[1]) * 100)}%` : "—");

  return (
    <>
      <div className="crumb"><a href="#/exams">考試</a> › 學生</div>
      <h1>{profile.student_name ?? "學生"}</h1>
      <p className="sub">歷次考試，選擇題與是非題分開看——是非題亂猜也有一半會對。</p>
      <div className="card" style={{ marginBottom: 14 }}>
        <h2>歷次成績</h2>
        <table>
          <thead><tr><th>考試</th><th>日期</th><th className="n">答對</th><th className="n">選擇題</th><th className="n">是非題</th></tr></thead>
          <tbody>
            {profile.results.map((r) => (
              <tr key={r.exam_uuid} className="link" onClick={() => go(`/exam/${r.exam_uuid}`)}>
                <td>{r.template_name}</td>
                <td>{r.exam_date}</td>
                <td className="n">{r.correct} / {r.total}</td>
                <td className="n">{rate(r.choice)}</td>
                <td className="n">{rate(r.mark)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {profile.results.slice(-1).map((r) => (
        <div className="card" key={r.exam_uuid}>
          <h2>最近一次錯的題目 <span>{r.template_name}</span></h2>
          {r.wrong.length === 0 ? <div className="note">全對。</div> : (
            <table>
              <thead><tr><th>題</th><th>寫了</th><th>答案</th></tr></thead>
              <tbody>
                {r.wrong.map((w) => (
                  <tr key={w.question_no}><td>第 {w.question_no} 題</td><td>{label(w.chosen)}</td><td>{label(w.key)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      ))}
    </>
  );
}
