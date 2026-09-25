import { Exam } from "./api";
import { go } from "./App";

export default function ExamList({ exams }: { exams: Exam[] | null }) {
  if (exams === null) return <div className="empty">載入中…</div>;
  return (
    <>
      <h1>考試</h1>
      <p className="sub">每一次考試是一個班、一天、一份考卷。</p>
      {exams.length === 0 ? (
        <div className="card empty">還沒有考試。在 App 掃描前先選擇班級，這裡就會出現。</div>
      ) : (
        <div className="list">
          {exams.map((e) => (
            <button key={e.client_uuid} className="row" onClick={() => go(`/exam/${e.client_uuid}`)}>
              <div className="grow">
                <div className="t">{e.template_name}{e.sitting > 1 ? `（第 ${e.sitting} 次）` : ""}</div>
                <div className="m">{e.class_name}・{e.exam_date}{e.unit ? `・單元 ${e.unit}` : ""}</div>
              </div>
              {e.is_simulated && <span className="chip sim">模擬資料</span>}
              <span className="chip">{e.paper_count} 份</span>
              {e.identified_count < e.paper_count && (
                <span className="chip warn">{e.paper_count - e.identified_count} 份未配對</span>
              )}
            </button>
          ))}
        </div>
      )}
    </>
  );
}
