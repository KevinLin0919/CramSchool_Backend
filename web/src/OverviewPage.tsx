import { useEffect, useState } from "react";
import { api, Overview } from "./api";
import { go, pct } from "./App";
import { LineChart, Sparkline } from "./charts";

const WEEKDAYS = "日一二三四五六";

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api.overview().then(setData).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="card empty">{error}</div>;
  if (!data) return <div className="empty">載入中…</div>;

  const now = new Date();
  const hour = now.getHours();
  const greet = hour < 11 ? "早安" : hour < 18 ? "午安" : "晚安";
  const focus = data.classes.find((c) => c.trend.length > 1) ?? data.classes[0];

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

      <div className="row3">
        {data.classes.slice(0, data.todo.length ? 2 : 3).map((c) => {
          const last = c.trend[c.trend.length - 1];
          return (
            <button key={c.id} type="button" className="classcard" onClick={() => go(`/class/${c.id}`)}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 17, fontWeight: 900 }}>{c.name} {c.is_simulated && <span className="pill sim">模擬</span>}</span>
                <span className="note">{c.students} 人</span>
              </div>
              <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between" }}>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span className="note">最近一次{last?.unit ? ` · ${last.unit}` : ""}</span>
                  <span style={{ fontSize: 28, fontWeight: 900 }}>{last ? pct(last.mean_rate) : "—"}</span>
                </div>
                <Sparkline values={c.trend.map((t) => t.mean_rate)} />
              </div>
            </button>
          );
        })}
        {data.todo.length > 0 && (
          <div className="todo">
            <span style={{ fontSize: 15, fontWeight: 900, color: "var(--bad-d)" }}>等你處理</span>
            {data.todo.slice(0, 3).map((t, i) => (
              <button key={i} type="button" onClick={() => go(`/exam/${t.exam_uuid}`)}>{t.text}<span>{t.kind === "match" ? "配對" : "查看"}</span></button>
            ))}
          </div>
        )}
      </div>

      <div className="row2" style={{ gridTemplateColumns: "minmax(0,1.25fr) minmax(0,1fr)" }}>
        <section className="card">
          <div className="title"><h2>最近的考試</h2><a href="#/exams" style={{ fontSize: 13, fontWeight: 700 }}>全部考試</a></div>
          <div className="table">
            <div className="tr th" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1.1fr) 50px 124px 100px" }}><span>考試</span><span>班級</span><span className="n">份數</span><span>平均答對</span><span>狀態</span></div>
            {data.recent.slice(0, 6).map((e) => (
              <button key={e.uuid} type="button" className="tr" style={{ gridTemplateColumns: "minmax(0,2fr) minmax(0,1.1fr) 50px 124px 100px" }} onClick={() => go(`/exam/${e.uuid}`)}>
                <span><b>{e.template_name}</b><small>{e.exam_date}</small></span>
                <span style={{ color: "var(--ink2)" }}>{e.class_name}</span>
                <span className="n">{e.papers}</span>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="meter" style={{ width: 56 }}><i style={{ width: `${e.mean && e.total ? (e.mean / e.total) * 100 : 0}%`, background: "var(--choice)" }} /></span>
                  <b style={{ fontSize: 13 }}>{e.mean ?? "—"} / {e.total}</b>
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
            <div className="title"><h2>{focus.name} · 各單元</h2><span>全班答對率</span></div>
            <LineChart onPoint={(i) => go(`/exam/${focus.trend[i].exam_uuid}`)}
              height={300}
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
