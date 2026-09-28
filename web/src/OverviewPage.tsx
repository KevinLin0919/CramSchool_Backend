import { useEffect, useState } from "react";
import { api, Overview, Trend } from "./api";
import { go, pct } from "./App";
import { LineChart, Sparkline } from "./charts";
import { watchReason } from "./StudentsPage";

const WEEKDAYS = "日一二三四五六";

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [trend, setTrend] = useState<Trend | null>(null);
  useEffect(() => { api.overview().then(setData).catch((e) => setError(e.message)); }, []);
  const focusId = data ? (data.classes.find((c) => c.trend.length > 1) ?? data.classes[0])?.id : undefined;
  useEffect(() => { if (focusId) api.trend(focusId).then(setTrend).catch(() => setTrend(null)); }, [focusId]);
  if (error) return <div className="card empty">{error}</div>;
  if (!data) return <div className="empty">載入中…</div>;

  const now = new Date();
  const hour = now.getHours();
  const greet = hour < 11 ? "早安" : hour < 18 ? "午安" : "晚安";
  const focus = data.classes.find((c) => c.id === focusId);
  const order = new Map(trend?.exams.map((e, i) => [e.exam_uuid, i]) ?? []);
  const watching = trend?.students.filter((s) => watchReason([...s.results]
    .sort((a, b) => (order.get(a.exam_uuid) ?? 0) - (order.get(b.exam_uuid) ?? 0)).map((r) => r.rate))).length ?? null;
  const unmatched = data.recent.reduce((a, e) => a + e.unmatched, 0);
  const cols = "minmax(0,2fr) minmax(0,1.1fr) 50px 150px 100px";

  return (
    <>
      <div className="head">
        <div>
          <span className="crumb">{now.getFullYear()} 年 {now.getMonth() + 1} 月 {now.getDate()} 日 星期{WEEKDAYS[now.getDay()]}</span>
          <h1>{greet}，{data.teacher}</h1>
          <span style={{ color: "var(--ink2)" }}>
            最近批改了 {data.exams_recent} 次考試、{data.papers_recent} 份考卷{data.todo.length ? `，有 ${data.todo.length} 件事等你處理。` : "。"}
          </span>
        </div>
      </div>

      <div className="ov">
        {focus && (() => {
          const last = focus.trend[focus.trend.length - 1];
          return (
            <button type="button" className="classcard" onClick={() => go(`/class/${focus.id}`)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 17, fontWeight: 700 }}>{focus.name}</span>
                <span className="note">{focus.students} 人</span>
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span className="note">最近一次{last?.unit ? ` · ${last.unit}` : ""}</span>
                  <span className="num" style={{ fontSize: 28, fontWeight: 700 }}>{last ? pct(last.mean_rate) : "—"}</span>
                </div>
                <Sparkline values={focus.trend.map((t) => t.mean_rate)} />
              </div>
            </button>
          );
        })()}
        <button type="button" className="statcard" onClick={() => go(focus ? `/students/${focus.id}` : "/students")}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 17, fontWeight: 700 }}>學生狀況</span>
            <span className="note">看全部學生 →</span>
          </div>
          <div style={{ display: "flex", gap: 28 }}>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="note">需要關注</span>
              <span className="big" style={{ color: watching ? "var(--bad-d)" : undefined }}>{watching ?? "—"}<small>位</small></span>
            </div>
            <div style={{ display: "flex", flexDirection: "column" }}>
              <span className="note">未配對考卷</span>
              <span className="big" style={{ color: unmatched ? "var(--warn)" : undefined }}>{unmatched}<small>份</small></span>
            </div>
          </div>
        </button>
        <div className={`todo ${data.todo.length ? "" : "clear"}`}>
          <span style={{ fontSize: 15, fontWeight: 700, color: data.todo.length ? "var(--bad-d)" : "var(--ink)" }}>等你處理</span>
          {data.todo.slice(0, 3).map((t, i) => (
            <button key={i} type="button" onClick={() => go(`/exam/${t.exam_uuid}`)}>{t.text}<span>{t.kind === "match" ? "配對" : "查看"}</span></button>
          ))}
          {data.todo.length === 0 && <span className="note">目前沒有需要處理的事。</span>}
        </div>

        <section className="card wide">
          <div className="title"><h2>最近的考試</h2><a href="#/exams" style={{ fontSize: 13, fontWeight: 700 }}>全部考試</a></div>
          <div className="table">
            <div className="tr th" style={{ gridTemplateColumns: cols }}><span>考試</span><span>班級</span><span className="n">份數</span><span>平均答對</span><span>狀態</span></div>
            {data.recent.slice(0, 6).map((e) => (
              <button key={e.uuid} type="button" className="tr" style={{ gridTemplateColumns: cols }} onClick={() => go(`/exam/${e.uuid}`)}>
                <span><b>{e.template_name}</b><small>{e.exam_date}</small></span>
                <span style={{ color: "var(--ink2)" }}>{e.class_name}</span>
                <span className="n">{e.papers}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}>
                  <span className="meter" style={{ width: 48 }}><i style={{ width: `${e.mean && e.total ? (e.mean / e.total) * 100 : 0}%`, background: "var(--choice)" }} /></span>
                  <b className="num" style={{ fontSize: 13 }}>{e.mean === null ? "—" : Math.round(e.mean * 10) / 10}<span className="note" style={{ fontWeight: 400 }}> / {e.total}</span></b>
                </span>
                <span>
                  {e.unmatched ? <span className="pill warn">{e.unmatched} 份未配對</span>
                    : e.flagged.length ? <span className="pill bad">{e.flagged.length} 題需確認</span>
                    : <span className="pill ok">完成</span>}
                </span>
              </button>
            ))}
            {data.recent.length === 0 && <div className="empty">還沒有考試。在 App 掃描前先選擇班級，這裡就會出現。</div>}
          </div>
        </section>
        {focus && (
          <section className="card">
            <div className="title"><h2>各單元答對率</h2><span>{focus.name}</span></div>
            <LineChart onPoint={(i) => go(`/exam/${focus.trend[i].exam_uuid}`)}
              height={260}
              labels={focus.trend.map((t) => t.unit ?? t.exam_date)}
              series={[
                { label: "是非題", color: "var(--mark)", values: focus.trend.map((t) => t.mark_rate) },
                { label: "選擇題", color: "var(--choice)", values: focus.trend.map((t) => t.choice_rate) },
                { label: "整體", color: "#16211b", values: focus.trend.map((t) => t.mean_rate), emphasis: true },
              ]}
            />
          </section>
        )}
      </div>
    </>
  );
}
