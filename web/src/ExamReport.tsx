import { useEffect, useState } from "react";
import { api, ItemStat, ItemStudents, Report } from "./api";
import { go } from "./App";
import { Histogram, ItemBars } from "./charts";
import AiPanel from "./AiPanel";

const FLAG_TEXT: Record<string, string> = {
  unanimous_wrong: "全部作答的人選了同一個錯的答案，先確認標準答案",
  popular_distractor: "多數人被同一個錯誤選項吸引",
  below_chance: "是非題答對率低於亂猜",
  negative_discrimination: "高分組反而答錯較多，題目可能有問題",
};

function pct(k: number, n: number) {
  return n ? `${Math.round((k / n) * 100)}%` : "—";
}

export default function ExamReport({ uuid }: { uuid: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);

  useEffect(() => {
    setReport(null);
    api.report(uuid).then((r) => {
      setReport(r);
      const flagged = r.items.find((i) => i.flags.some((f) => f !== "guessable"));
      setSelected((flagged ?? r.items[0])?.question_no ?? null);
    }).catch((e) => setError(e.message));
  }, [uuid]);

  if (error) return <div className="card empty">{error}</div>;
  if (!report) return <div className="empty">載入中…</div>;

  const small = report.small_group;
  const item = report.items.find((i) => i.question_no === selected) ?? null;
  const n = report.papers;

  return (
    <>
      <div className="crumb"><a href="#/exams">考試</a> › {report.exam.class_name}</div>
      <h1>{report.exam.template_name}</h1>
      <p className="sub">
        {report.exam.class_name}・{report.exam.exam_date}
        {report.exam.unit ? `・單元 ${report.exam.unit}` : ""}{" "}
        {report.exam.is_simulated && <span className="chip sim">模擬資料</span>}{" "}
        <span className={report.identified === n ? "chip ok" : "chip warn"}>{report.identified}/{n} 份已配對學生</span>{" "}
        {report.pending_cells > 0 && <span className="chip warn">{report.pending_cells} 格未確認</span>}
      </p>

      <div className="kpis">
        <div className="kpi"><div className="l">平均答對</div><div className="v">{report.mean ?? "—"}<small> / {report.total}</small></div><div className="s">中位數 {report.median ?? "—"}</div></div>
        <div className="kpi"><div className="l">選擇題</div><div className="v">{small ? `${report.choice.correct}` : pct(report.choice.correct, report.choice.total)}<small>{small ? ` / ${report.choice.total}` : ""}</small></div><div className="s">全班答對{small ? "格數" : "率"}</div></div>
        <div className="kpi"><div className="l">是非題</div><div className="v">{small ? `${report.mark.correct}` : pct(report.mark.correct, report.mark.total)}<small>{small ? ` / ${report.mark.total}` : ""}</small></div><div className="s">亂猜也有一半會對</div></div>
        <div className="kpi"><div className="l">值得注意的題目</div><div className="v">{report.items.filter((i) => i.flags.some((f) => f !== "guessable")).length}<small> 題</small></div><div className="s">點下方長條查看</div></div>
      </div>

      {small && (
        <div className="callout" style={{ marginBottom: 14 }}>
          這次只有 {n} 份，少於 10 份時只顯示人數，不計算百分比與鑑別度。
        </div>
      )}

      <div className="grid2">
        <div className="stack">
          <div className="card">
            <h2>每題答對比例 <span>點一題看細節</span></h2>
            <ItemBars
              items={report.items.map((i) => ({ q: i.question_no, type: i.answer_type, correct: i.correct, answered: i.answered, flagged: i.flags.some((f) => f !== "guessable") }))}
              selected={selected}
              onSelect={setSelected}
            />
            <div className="legend">
              <span><i style={{ background: "var(--brand-m)" }} />選擇題</span>
              <span><i style={{ background: "var(--mark)" }} />是非題</span>
              <span><i style={{ background: "var(--bad)" }} />值得注意</span>
            </div>
          </div>
          <div className="card">
            <h2>答對題數分布 <span>{n} 份</span></h2>
            <Histogram data={report.distribution} total={report.total} />
          </div>
          <div className="card">
            <h2>學生 <span>依答對題數</span></h2>
            <table>
              <thead><tr><th>學生</th><th className="n">答對</th><th className="n">未確認</th></tr></thead>
              <tbody>
                {[...report.paper_list].sort((a, b) => b.correct - a.correct).map((p) => (
                  <tr key={p.session_uuid} className={p.student_id ? "link" : ""} onClick={() => p.student_id && go(`/student/${p.student_id}`)}>
                    <td>{p.student_name ?? <span style={{ color: "var(--ink3)" }}>未配對</span>}</td>
                    <td className="n">{p.correct} / {report.total}</td>
                    <td className="n">{p.pending || ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <div className="stack">
          {item && <ItemDetail uuid={uuid} item={item} small={small} />}
          {item && <AiPanel examUuid={uuid} item={item} />}
        </div>
      </div>
    </>
  );
}

function ItemDetail({ uuid, item, small }: { uuid: string; item: ItemStat; small: boolean }) {
  const [who, setWho] = useState<ItemStudents | null>(null);
  const [option, setOption] = useState<string | null>(null);

  useEffect(() => {
    setWho(null);
    setOption(item.top_wrong?.option ?? null);
    api.itemStudents(uuid, item.question_no).then(setWho).catch(() => setWho(null));
  }, [uuid, item.question_no, item.top_wrong?.option]);

  const max = Math.max(1, ...Object.values(item.options));
  const label = (o: string) => (o === "O" ? "○" : o === "X" ? "✕" : o);
  const flags = item.flags.filter((f) => f !== "guessable");

  return (
    <div className="card">
      <h2>
        第 {item.question_no} 題・{item.answer_type === "choice" ? "選擇題" : "是非題"}
        <span>標準答案 {label(item.key)}</span>
      </h2>
      {Object.entries(item.options).map(([o, c]) => (
        <button key={o} className={`opt ${option === o ? "sel" : ""}`} onClick={() => setOption(o)}>
          <b>{label(o)}</b>
          <span className="bar"><i className={o === item.key ? "key" : item.top_wrong?.option === o ? "lure" : ""} style={{ width: `${(c / max) * 100}%` }} /></span>
          <em>{small ? `${c} 人` : `${c} 人・${pct(c, item.answered)}`}</em>
        </button>
      ))}
      <div className="note">
        作答 {item.answered} 人{item.blank ? `・空白 ${item.blank}` : ""}{item.pending ? `・未確認 ${item.pending}` : ""}
        {item.discrimination !== null ? `・鑑別度 ${item.discrimination.toFixed(2)}` : ""}
        {item.unchosen.length > 0 ? `・沒人選：${item.unchosen.map(label).join("、")}` : ""}
      </div>
      {item.high_low && (
        <div className="note">
          高分組 {item.high_low.high_n} 人選 {Object.entries(item.high_low.high).filter(([, c]) => c).map(([o, c]) => `${label(o)}:${c}`).join(" ")}
          ｜低分組 {item.high_low.low_n} 人選 {Object.entries(item.high_low.low).filter(([, c]) => c).map(([o, c]) => `${label(o)}:${c}`).join(" ")}
        </div>
      )}
      {flags.map((f) => <div key={f} className="callout">{FLAG_TEXT[f] ?? f}</div>)}
      {option && who && (
        <>
          <div className="note" style={{ marginTop: 12 }}>選 {label(option)} 的學生</div>
          <div className="names">
            {(who.groups[option] ?? []).map((s) => <span key={s.session_uuid}>{s.student_name ?? "未配對"}</span>)}
            {(who.groups[option] ?? []).length === 0 && <span>沒有</span>}
          </div>
        </>
      )}
    </div>
  );
}
