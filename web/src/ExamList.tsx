import { useEffect, useState } from "react";
import { api, Exam } from "./api";
import { go } from "./App";

export default function ExamList() {
  const [exams, setExams] = useState<Exam[] | null>(null);
  useEffect(() => { api.exams().then(setExams).catch(() => setExams([])); }, []);
  if (exams === null) return <div className="empty">載入中…</div>;
  return (
    <>
      <div className="head"><div><span className="crumb">考試</span><h1>所有考試</h1><span style={{ color: "var(--ink2)" }}>一次考試是一個班、一天、一份考卷。</span></div></div>
      <section className="card">
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: "minmax(0,2.4fr) minmax(0,1fr) 90px 80px 130px" }}><span>考試</span><span>班級</span><span>單元</span><span className="n">份數</span><span>狀態</span></div>
          {exams.map((e) => (
            <button key={e.client_uuid} type="button" className="tr" style={{ gridTemplateColumns: "minmax(0,2.4fr) minmax(0,1fr) 90px 80px 130px" }} onClick={() => go(`/exam/${e.client_uuid}`)}>
              <span><b>{e.template_name}{e.sitting > 1 ? `（第 ${e.sitting} 次）` : ""}</b><small>{e.exam_date}</small></span>
              <span style={{ color: "var(--ink2)" }}>{e.class_name} {e.is_simulated && <span className="pill sim">模擬</span>}</span>
              <span>{e.unit ?? "—"}</span>
              <span className="n">{e.paper_count}</span>
              <span>{e.identified_count < e.paper_count ? <span className="pill warn">{e.paper_count - e.identified_count} 份未配對</span> : <span className="pill ok">已配對</span>}</span>
            </button>
          ))}
          {exams.length === 0 && <div className="empty">還沒有考試。</div>}
        </div>
      </section>
    </>
  );
}
