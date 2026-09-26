import { useEffect, useMemo, useState } from "react";
import { api, ItemStat, ItemStudents, Report } from "./api";
import { go, label, pct } from "./App";
import { GroupBars, Histogram, ItemBars } from "./charts";
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

  function load() {
    api.report(uuid).then((r) => {
      setReport(r);
      setSelected((s) => s ?? (r.items.find(notable) ?? r.items[0])?.question_no ?? null);
    }).catch((e) => setError(e.message));
  }
  useEffect(() => { setReport(null); setSelected(null); load(); }, [uuid]); // eslint-disable-line

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
            {report.exam.is_simulated && <span className="pill sim">模擬資料</span>}
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
          <span className="s">亂猜也有 50%</span>
        </div>
        <div className={`kpi ${flagged.length ? "alert" : ""}`}>
          <span className="l">值得注意的題目</span>
          <span className="v">{flagged.length}<small>題</small></span>
          <span className="s">{flagged.length ? flagged.slice(0, 3).map((i) => `第 ${i.question_no} 題`).join("、") : "沒有異常"}</span>
        </div>
      </div>

      {small && <div className="callout" style={{ background: "var(--warn-s)", color: "var(--warn)" }}>這次只有 {n} 份。少於 10 份時只顯示人數，不計算百分比與鑑別度。</div>}

      <div className="row2">
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
            items={items.map((i) => ({ q: i.question_no, type: i.answer_type, rate: i.answered ? i.correct / i.answered : 0, flagged: notable(i) }))}
            selected={selected}
            onSelect={setSelected}
          />
          <div className="legend">
            <span><i style={{ background: "var(--mark-l)" }} />是非題</span>
            <span><i style={{ background: "var(--choice)" }} />選擇題</span>
            <span><i style={{ background: "var(--bad)" }} />值得注意</span>
          </div>
        </section>
        <ExamSummary examUuid={uuid} />
      </div>

      <div className="row2">
        {item ? <ItemDetail uuid={uuid} item={item} small={small} /> : <div />}
        <div className="col">
          <section className="card">
            <div className="title"><h2>答對題數分布</h2><span>{n} 份</span></div>
            <Histogram data={report.distribution} total={report.total} mark={report.median} />
          </section>
          <section className="card">
            <div className="title"><h2>需要關注</h2><span>比自己平常低 15% 以上</span></div>
            {report.watch.length === 0 && <span className="note">{report.previous ? "沒有學生明顯退步。" : "第一次考試，還沒有可以比較的紀錄。"}</span>}
            {report.watch.slice(0, 5).map((w) => (
              <button key={w.student_id} type="button" className="watch" onClick={() => go(`/student/${w.student_id}`)}>
                <span className="avatar">{(w.student_name ?? "?").slice(0, 1)}</span>
                <span><b>{w.student_name}</b><small>平常 {pct(w.usual_rate)} → 這次 {pct(w.rate)}</small></span>
                <em>−{Math.round(w.drop * 100)}%</em>
              </button>
            ))}
          </section>
          <section className="card">
            <div className="title"><h2>學生</h2><span>依答對題數</span></div>
            <div className="table">
              {[...report.paper_list].sort((a, b) => b.correct - a.correct).slice(0, allStudents ? undefined : 8).map((p) => (
                <button key={p.session_uuid} type="button" className="tr" disabled={!p.student_id} style={{ gridTemplateColumns: "minmax(0,1fr) 110px 60px", padding: "8px 10px" }} onClick={() => p.student_id && go(`/student/${p.student_id}`)}>
                  <span>{p.student_name ?? <span className="note">未配對</span>}</span>
                  <span style={{ display: "flex", alignItems: "center", gap: 8 }}><span className="meter" style={{ width: 50 }}><i style={{ width: `${(p.correct / report.total) * 100}%`, background: "var(--choice)" }} /></span>{p.correct}/{report.total}</span>
                  <span className="n note">{p.pending ? `${p.pending} 待確認` : ""}</span>
                </button>
              ))}
            </div>
            {report.paper_list.length > 8 && (
              <button type="button" className="btn soft" style={{ alignSelf: "center" }} onClick={() => setAllStudents((v) => !v)}>
                {allStudents ? "收起" : `顯示全部 ${report.paper_list.length} 位`}
              </button>
            )}
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

  const max = Math.max(1, ...Object.values(item.options));
  const flags = item.flags.filter((f) => f !== "guessable");
  const options = Object.keys(item.options);
  const lure = item.top_wrong?.option ?? null;
  const tone = (o: string) => o === item.key ? ["var(--brand-s)", "var(--brand-d)", "var(--choice)"] : o === lure ? ["var(--bad-s)", "var(--bad-d)", "var(--bad)"] : ["var(--sunk)", "var(--ink2)", "#b9c3bd"];
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
            標準答案 {label(item.key)} · 作答 {item.answered} 人 · 答對 {item.correct} 人
            {item.discrimination !== null ? ` · 鑑別度 ${item.discrimination.toFixed(2)}` : ""}
            {item.pending ? ` · 待確認 ${item.pending}` : ""}
          </span>
        </div>
        <ExplainItem examUuid={uuid} questionNo={item.question_no} wrongLabel={lure ? label(lure) : null} />
      </div>
      {flags.includes("unanimous_wrong") && <div className="callout">作答的人全選了同一個錯誤答案，建議先確認標準答案有沒有設錯。</div>}
      <div className="split">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="caption">選項分布</span>
          {options.map((o) => {
            const [bg, fg, bar] = tone(o);
            const c = item.options[o];
            return (
              <button key={o} type="button" className={`optrow ${option === o ? "sel" : ""}`} onClick={() => setOption(o)}>
                <span className="chip" style={{ background: bg, color: fg }}>{label(o)}</span>
                <span className="hbar"><i style={{ width: `${(c / max) * 100}%`, background: bar }} /></span>
                <em><b>{c}</b> 人{small ? "" : ` · ${pct(item.answered ? c / item.answered : null)}`}</em>
              </button>
            );
          })}
          {item.unchosen.length > 0 && <span className="note">沒有人選：{item.unchosen.map(label).join("、")}</span>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <span className="caption">高分組 vs 低分組（各 27%）</span>
          {item.high_low ? (
            <>
              <GroupBars options={options} high={item.high_low.high} low={item.high_low.low} label={label} />
              <div className="legend">
                <span><i style={{ background: "var(--brand)" }} />高分組 {item.high_low.high_n} 人</span>
                <span><i style={{ background: "#b7c9bd" }} />低分組 {item.high_low.low_n} 人</span>
              </div>
            </>
          ) : <span className="note">少於 10 份，不分組比較。</span>}
        </div>
      </div>
      {option && (
        <div className="box">
          <span className="caption">選 {label(option)} 的 {picked.length} 位學生</span>
          <div className="names">
            {picked.map((s) => <span key={s.session_uuid}>{s.student_name ?? "未配對"}</span>)}
            {picked.length === 0 && <span className="note">沒有</span>}
          </div>
        </div>
      )}
    </section>
  );
}
