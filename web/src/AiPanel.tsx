import { useEffect, useState } from "react";
import { AiRun, api, Sentence, settle } from "./api";
import { Icon } from "./icons";

// Every number the AI states comes from the server's statistics; a sentence
// where the model wrote a figure of its own is shown but marked 未驗證.
export function Sentences({ items }: { items: Sentence[] }) {
  return (
    <>
      {items.map((s, i) => (
        <span key={i} className={s.verified ? "" : "unverified"} title={s.verified ? undefined : "這句的數字不是系統算的，未經驗證"}>
          {s.text}{!s.verified && <sup className="uv">未驗證</sup>}
        </span>
      ))}
    </>
  );
}

export function useAiStatus() {
  const [status, setStatus] = useState<{ configured: boolean; model: string } | null>(null);
  useEffect(() => { api.aiStatus().then(setStatus).catch(() => setStatus({ configured: false, model: "" })); }, []);
  return status;
}

export function useRun() {
  const [run, setRun] = useState<AiRun | null>(null);
  const [error, setError] = useState("");
  async function start(fn: () => Promise<AiRun>) {
    setError("");
    setRun(null);
    try {
      const first = await fn();
      setRun(first);
      setRun(await settle(first, setRun));
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI 沒有回答");
    }
  }
  const busy = !!run && (run.status === "pending" || run.status === "running");
  const failed = run?.status === "failed" ? run.error ?? "AI 沒有回答" : error;
  return { run, start, busy, failed, done: run?.status === "done" ? run.answer : null, reset: () => { setRun(null); setError(""); } };
}

function Header({ title, tag }: { title: string; tag?: string }) {
  return (
    <div className="top">
      <div><span className="spark"><Icon.sparkle color="#e4efe8" /></span><h2>{title}</h2></div>
      {tag && <span className="tag">{tag}</span>}
    </div>
  );
}

export function ExamSummary({ examUuid }: { examUuid: string }) {
  const status = useAiStatus();
  const summary = useRun();
  const ask = useRun();
  const [q, setQ] = useState("");
  useEffect(() => { summary.reset(); ask.reset(); }, [examUuid]); // eslint-disable-line

  if (status && !status.configured) {
    return (
      <section className="ai">
        <Header title="AI 考試摘要" />
        <p className="note">伺服器尚未設定 AI 金鑰。設定後，這裡會寫出這次考試的重點與下堂課建議。</p>
      </section>
    );
  }
  const a = summary.done;
  return (
    <section className="ai">
      <Header title="AI 考試摘要" tag="AI 草稿" />
      {!a && !summary.busy && (
        <button type="button" className="btn primary" style={{ alignSelf: "flex-start" }} onClick={() => summary.start(() => api.summary(examUuid))}>
          <Icon.sparkle />產生摘要
        </button>
      )}
      {summary.busy && <p className="note">AI 正在整理這次考試…（通常 10–30 秒）</p>}
      {summary.failed && <p className="err">{summary.failed}</p>}
      {a && (
        <>
          <p><Sentences items={a.summary} /></p>
          {a.focus?.length > 0 && (
            <>
              <div className="sub">下堂課建議</div>
              {a.focus.map((f: Sentence[], i: number) => <div key={i} className="step"><b>{i + 1}</b><span><Sentences items={f} /></span></div>)}
            </>
          )}
        </>
      )}
      <form className="ask" onSubmit={(e) => { e.preventDefault(); if (q.trim().length > 1) ask.start(() => api.ask(examUuid, q.trim())); }}>
        <input id="ask" value={q} onChange={(e) => setQ(e.target.value)} placeholder="問這次考試，例如：誰需要多注意？" maxLength={300} aria-label="問這次考試" />
        <button type="submit" aria-label="送出問題" disabled={ask.busy}><Icon.send /></button>
      </form>
      {ask.busy && <p className="note">AI 正在查資料…</p>}
      {ask.failed && <p className="err">{ask.failed}</p>}
      {ask.done && <p><Sentences items={ask.done.answer} /></p>}
    </section>
  );
}

export function ExplainItem({ examUuid, questionNo, wrongLabel }: { examUuid: string; questionNo: number; wrongLabel: string | null }) {
  const status = useAiStatus();
  const r = useRun();
  useEffect(() => { r.reset(); }, [examUuid, questionNo]); // eslint-disable-line
  if (!status?.configured) return null;
  const a = r.done;
  return (
    <>
      {!a && (
        <button type="button" className="btn soft" disabled={r.busy} onClick={() => r.start(() => api.explain(examUuid, questionNo))}>
          <Icon.sparkle color="var(--brand)" size={14} />{r.busy ? "AI 思考中…" : wrongLabel ? `為什麼大家選 ${wrongLabel}？` : "AI 解釋這一題"}
        </button>
      )}
      {r.failed && <span className="err">{r.failed}</span>}
      {a && (
        <div className="ai" style={{ padding: "14px 16px", gap: 8 }}>
          {a.key_check && <div className="callout">建議先確認這題的標準答案有沒有設錯。</div>}
          <p><b>考什麼：</b><Sentences items={a.concept} /></p>
          <p><b>為什麼：</b><Sentences items={a.why} /></p>
          <p><b>下堂課：</b><Sentences items={a.suggestion} /></p>
          {!a.saw_question && <span className="note">讀不到這題的題目區塊，解釋只根據作答數字。</span>}
        </div>
      )}
    </>
  );
}

export function ParentNote({ studentId }: { studentId: number }) {
  const status = useAiStatus();
  const r = useRun();
  const [copied, setCopied] = useState(false);
  useEffect(() => { r.reset(); setCopied(false); }, [studentId]); // eslint-disable-line
  if (!status?.configured) return null;
  const text = r.done ? (r.done.note as Sentence[]).map((s) => s.text).join("") : "";
  return (
    <section className="ai" style={{ flexDirection: "row", alignItems: "flex-start", gap: 18 }}>
      <span className="spark" style={{ width: 36, height: 36 }}><Icon.sparkle color="#e4efe8" size={18} /></span>
      <div style={{ display: "flex", flexDirection: "column", gap: 8, flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}><h2>給家長的一段話</h2><span className="tag">AI 草稿，送出前請修改</span></div>
        {r.done ? <p><Sentences items={r.done.note} /></p> : r.busy ? <p className="note">AI 撰寫中…</p> : <p className="note">根據這位學生歷次考試，寫一段可以傳給家長的話。</p>}
        {r.failed && <p className="err">{r.failed}</p>}
      </div>
      {r.done ? (
        <button type="button" className="btn primary" onClick={async () => { try { await navigator.clipboard.writeText(text); setCopied(true); } catch { setCopied(false); } }}>{copied ? "已複製" : "複製"}</button>
      ) : (
        <button type="button" className="btn primary" disabled={r.busy} onClick={() => r.start(() => api.parentNote(studentId))}>產生</button>
      )}
    </section>
  );
}
