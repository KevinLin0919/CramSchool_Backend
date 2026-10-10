import { useEffect, useMemo, useState } from "react";
import { api, ClassRoster, ItemStat, ItemStudents, Report } from "./api";
import { go, label, pct } from "./App";
import { GroupBars, Histogram, ItemBars, OptionBars } from "./charts";
import { ExamSummary, ExplainItem } from "./AiPanel";

const FLAG_TEXT: Record<string, string> = {
  unanimous_wrong: "作答的人全選了同一個錯誤答案",
  popular_distractor: "多數人被同一個錯誤選項吸引",
  below_chance: "是非題答對率低於亂猜",
  negative_discrimination: "高分組反而錯得較多",
};
const notable = (i: ItemStat) => i.flags.some((f) => f !== "guessable");

export default function ExamReport({ uuid }: { uuid: string }) {
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState<"all" | "mark" | "choice">("all");
  const [regrading, setRegrading] = useState(false);
  const [allStudents, setAllStudents] = useState(false);
  const [scoreFilter, setScoreFilter] = useState<number | null>(null);
  const [roster, setRoster] = useState<ClassRoster | null>(null);
  const [assigning, setAssigning] = useState<string | null>(null);

  function load() {
    api.report(uuid).then((r) => {
      setReport(r);
      setSelected((s) => s ?? (r.items.find(notable) ?? r.items[0])?.question_no ?? null);
    }).catch((e) => setError(e.message));
  }
  useEffect(() => { setReport(null); setSelected(null); setScoreFilter(null); load(); }, [uuid]); // eslint-disable-line
  const classId = report?.exam.class_id;
  useEffect(() => {
    if (classId === undefined) return;
    api.classes().then((cs) => setRoster(cs.find((c) => c.id === classId) ?? null)).catch(() => setRoster(null));
  }, [classId]);

  async function assign(sessionUuid: string, studentId: number) {
    setAssigning(sessionUuid);
    try { await api.assign(sessionUuid, studentId); load(); }
    catch (e) { setError(e instanceof Error ? e.message : "配對失敗"); }
    finally { setAssigning(null); }
  }

  const items = useMemo(() => (report?.items ?? []).filter((i) => filter === "all" || i.answer_type === filter), [report, filter]);
  if (error) return <div className="card empty">{error}</div>;
  if (!report) return <div className="empty">載入中…</div>;

  const n = report.papers, small = report.small_group;
  const item = report.items.find((i) => i.question_no === selected) ?? null;
  const flagged = report.items.filter(notable);
  const meanRate = report.mean !== null && report.total ? report.mean / report.total : null;
  const delta = report.previous && meanRate !== null ? meanRate - report.previous.mean_rate : null;
  const counts = { all: report.items.length, mark: report.items.filter((i) => i.answer_type === "mark").length, choice: report.items.filter((i) => i.answer_type === "choice").length };
  const best = Math.max(...report.paper_list.map((p) => p.correct), 0);
  const worst = Math.min(...report.paper_list.map((p) => p.correct), best);
  const unmatched = report.paper_list.filter((p) => !p.student_id);
  const matched = new Set(report.paper_list.map((p) => p.student_id).filter((id): id is number => id !== null));

  return (
    <>
      <div className="head">
        <div>
          <span className="crumb"><a href="#/exams">考試</a> / {report.exam.class_name}</span>
          <h1>{report.exam.template_name}</h1>
          <div className="meta">
            <span>{report.exam.exam_date}</span>
            {report.exam.unit && <><span className="dot">·</span><span>單元 {report.exam.unit}</span></>}
            <span className="dot">·</span><span>{n} 份</span>
            <span className={report.identified === n ? "pill ok" : "pill warn"}>{report.identified}/{n} 已配對學生</span>
            {report.pending_cells > 0 && <span className="pill warn">{report.pending_cells} 格待確認</span>}
          </div>
        </div>
        <button type="button" className="btn ghost" disabled={regrading} onClick={async () => {
          setRegrading(true);
          try { await api.regrade(uuid); load(); } catch (e) { setError(e instanceof Error ? e.message : "重新計分失敗"); }
          finally { setRegrading(false); }
        }}>{regrading ? "重新計分中…" : "依目前答案重新計分"}</button>
      </div>

      <div className="kpis">
        <div className="kpi">
          <span className="l">平均答對</span>
          <span className="v">{report.mean ?? "—"}<small>/ {report.total} 題</small></span>
          {delta !== null && report.previous
            ? <span className={`s ${delta < 0 ? "down" : "up"}`}>{delta < 0 ? "▼" : "▲"} {Math.abs(Math.round(delta * 100))}%　比 {report.previous.unit ?? "上一次"}</span>
            : <span className="s">第一次考試</span>}
        </div>
        <div className="kpi"><span className="l">中位數</span><span className="v">{report.median ?? "—"}<small>/ {report.total} 題</small></span><span className="s">最高 {best} · 最低 {worst}</span></div>
        <div className="kpi">
          <span className="l">選擇題{small ? "答對" : "答對率"}</span>
          <span className="v">{small ? <>{report.choice.correct}<small>/ {report.choice.total}</small></> : pct(report.choice.total ? report.choice.correct / report.choice.total : null)}</span>
          <span className="meter"><i style={{ width: `${report.choice.total ? (report.choice.correct / report.choice.total) * 100 : 0}%`, background: "var(--choice)" }} /></span>
        </div>
        <div className="kpi">
          <span className="l">是非題{small ? "答對" : "答對率"}</span>
          <span className="v">{small ? <>{report.mark.correct}<small>/ {report.mark.total}</small></> : pct(report.mark.total ? report.mark.correct / report.mark.total : null)}</span>
          <span className="meter"><i style={{ width: `${report.mark.total ? (report.mark.correct / report.mark.total) * 100 : 0}%`, background: "var(--mark)" }} /></span>
        </div>
        <div className={`kpi ${flagged.length ? "alert" : ""}`}>
          <span className="l">值得注意的題目</span>
          <span className="v">{flagged.length}<small>題</small></span>
          <span className="s">{flagged.length ? `第 ${flagged.slice(0, 6).map((i) => i.question_no).join("、")}${flagged.length > 6 ? " 等" : ""} 題` : "沒有異常"}</span>
        </div>
      </div>

      {small && <div className="callout" style={{ background: "var(--warn-s)", color: "var(--warn)" }}>這次只有 {n} 份。少於 10 份時只顯示人數，不計算百分比與鑑別度。</div>}

      <div className="cols">
        <div className="col">
          <section className="card">
            <div className="title" style={{ alignItems: "center" }}>
              <div><h2>每題答對率</h2><span className="note">點一題看選項分布與誰選了什麼</span></div>
              <div className="seg" role="group" aria-label="題型">
                {(["all", "mark", "choice"] as const).map((f) => (
                  <button key={f} type="button" className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
                    {f === "all" ? "全部" : f === "mark" ? "是非" : "選擇"} {counts[f]}
                  </button>
                ))}
              </div>
            </div>
            <ItemBars
              items={items.map((i) => ({ q: i.question_no, type: i.answer_type, correct: i.correct, answered: i.answered, flags: i.flags, flagged: notable(i) }))}
              selected={selected}
              onSelect={setSelected}
            />
            <div className="legend">
              <span><i style={{ background: "var(--mark-l)" }} />是非題</span>
              <span><i style={{ background: "var(--choice)" }} />選擇題</span>
              <span><i style={{ background: "var(--bad)" }} />值得注意</span>
              {counts.mark > 0 && <span><i className="dash" />亂猜基準 50%</span>}
            </div>
          </section>
          {item && <ItemDetail uuid={uuid} item={item} small={small} />}
          <section className="card">
            <div className="title" style={{ alignItems: "center" }}>
              <h2>學生</h2>
              {scoreFilter !== null
                ? <button type="button" className="filterchip" onClick={() => setScoreFilter(null)}>只看答對 {scoreFilter} 題 ✕</button>
                : <span>{unmatched.length ? `${unmatched.length} 份未配對，對照紙本的題數選學生` : "依答對題數"}</span>}
            </div>
            <div className="table">
              {/* Unmatched papers first, so 「配對」 from the overview lands on them.
                  第 N 份 is scan order — the same number the phone showed. */}
              {report.paper_list.map((p, i) => ({ ...p, position: i + 1 }))
                .filter((p) => scoreFilter === null || p.correct === scoreFilter)
                .sort((a, b) => Number(!!a.student_id) - Number(!!b.student_id) || b.correct - a.correct)
                .slice(0, allStudents ? undefined : Math.max(8, unmatched.length)).map((p) => {
                const score = (
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="meter" style={{ width: 50 }}><i style={{ width: `${(p.correct / report.total) * 100}%`, background: "var(--choice)" }} /></span>{p.correct}/{report.total}</span>
                );
                const pending = <span className="n note">{p.pending ? `${p.pending} 待確認` : ""}</span>;
                return p.student_id ? (
                  <button key={p.session_uuid} type="button" className="tr" style={{ gridTemplateColumns: "minmax(0,1fr) 110px 60px", padding: "8px 10px" }} onClick={() => go(`/student/${p.student_id}/${uuid}`)}>
                    <span>{p.student_name}</span>{score}{pending}
                  </button>
                ) : (
                  <div key={p.session_uuid} className="tr" style={{ gridTemplateColumns: "minmax(0,1fr) 110px 60px", padding: "8px 10px" }}>
                    <span style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                      <span className="note">第 {p.position} 份</span>
                      <select className="switch" aria-label={`第 ${p.position} 份是誰的`} value="" disabled={!roster || assigning === p.session_uuid}
                        onChange={(e) => e.target.value && assign(p.session_uuid, Number(e.target.value))}>
                        <option value="" disabled>{assigning === p.session_uuid ? "配對中…" : roster ? "選擇學生" : "載入名冊中…"}</option>
                        {roster?.students.filter((s) => !matched.has(s.id)).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                      </select>
                    </span>
                    {score}{pending}
                  </div>
                );
              })}
            </div>
            {scoreFilter === null && report.paper_list.length > Math.max(8, unmatched.length) && (
              <button type="button" className="btn soft" style={{ alignSelf: "center" }} onClick={() => setAllStudents((v) => !v)}>
                {allStudents ? "收起" : `顯示全部 ${report.paper_list.length} 位`}
              </button>
            )}
          </section>
        </div>
        <div className="col">
          <ExamSummary examUuid={uuid} />
          <section className="card">
            <div className="title"><h2>答對題數分布</h2><span>{n} 份</span></div>
            <Histogram data={report.distribution} total={report.total} median={report.median} mean={report.mean}
              selected={scoreFilter} onSelect={(c) => { setScoreFilter(c); setAllStudents(true); }} />
          </section>
          <section className="card">
            <div className="title"><h2>需要關注</h2><span>比自己平常低 15% 以上</span></div>
            {report.watch.length === 0 && <span className="note">{report.previous ? "沒有學生明顯退步。" : "第一次考試，還沒有可以比較的紀錄。"}</span>}
            {report.watch.slice(0, 5).map((w) => (
              <button key={w.student_id} type="button" className="watch" onClick={() => go(`/student/${w.student_id}/${uuid}`)}>
                <span className="avatar">{(w.student_name ?? "?").slice(0, 1)}</span>
                <span><b>{w.student_name}</b><small>平常 {pct(w.usual_rate)} → 這次 {pct(w.rate)}</small></span>
                <em>−{Math.round(w.drop * 100)}%</em>
              </button>
            ))}
          </section>
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
    setOption(item.top_wrong?.option ?? item.key);
    api.itemStudents(uuid, item.question_no).then(setWho).catch(() => setWho(null));
  }, [uuid, item.question_no, item.top_wrong?.option, item.key]);

  const flags = item.flags.filter((f) => f !== "guessable");
  const options = Object.keys(item.options);
  const lure = item.top_wrong?.option ?? null;
  // ○ and ✕ read as right and wrong at a glance; on a 是非 question they are
  // the answers 是 and 非, so say which.
  const optLabel = (o: string) => (item.answer_type === "mark" && (o === "O" || o === "X") ? `${label(o)} ${o === "O" ? "是" : "非"}` : label(o));
  const picked = option && who ? who.groups[option] ?? [] : [];

  return (
    <section className="card">
      <div className="title" style={{ alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <h2 style={{ fontSize: 18, fontWeight: 900 }}>第 {item.question_no} 題</h2>
            <span className="pill ok">{item.answer_type === "choice" ? "選擇題" : "是非題"}</span>
            {flags.map((f) => <span key={f} className="pill bad">{FLAG_TEXT[f] ?? f}</span>)}
          </div>
          <span style={{ fontSize: 13, color: "var(--ink2)" }}>
            標準答案 {optLabel(item.key)} · 作答 {item.answered} 人 · 答對 {item.correct} 人
            {item.discrimination !== null ? ` · 鑑別度 ${item.discrimination.toFixed(2)}` : ""}
            {item.pending ? ` · 待確認 ${item.pending}` : ""}
          </span>
        </div>
        <ExplainItem examUuid={uuid} questionNo={item.question_no} wrongLabel={lure ? label(lure) : null} />
      </div>
      {flags.includes("unanimous_wrong") && <div className="callout">作答的人全選了同一個錯誤答案，建議先確認標準答案有沒有設錯。</div>}
      <div className="split">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="caption">選項分布 <span className="note" style={{ fontWeight: 400 }}>· 綠色是正解、紅色是最多人選的錯誤選項 · 點選項看是誰選的</span></span>
          <OptionBars counts={item.options} answerKey={item.key} lure={lure} answered={item.answered} small={small}
            selected={option} onSelect={setOption} label={optLabel} />
          {item.unchosen.length > 0 && <span className="note">沒有人選：{item.unchosen.map(optLabel).join("、")}</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <span className="caption">高分組 vs 低分組（各 27%）</span>
          {item.high_low ? (
            <>
              <GroupBars options={options} high={item.high_low.high} low={item.high_low.low}
                highN={item.high_low.high_n} lowN={item.high_low.low_n} label={optLabel} />
            </>
          ) : <span className="note">少於 10 份，不分組比較。</span>}
        </div>
      </div>
      {option && (
        <div className="box">
          <span className="caption">選 {optLabel(option)} 的 {picked.length} 位學生</span>
          <div className="names">
            {picked.map((s) => <span key={s.session_uuid}>{s.student_name ?? "未配對"}</span>)}
            {picked.length === 0 && <span className="note">沒有</span>}
          </div>
        </div>
      )}
    </section>
  );
}
