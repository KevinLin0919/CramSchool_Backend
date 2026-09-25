import { useEffect, useState } from "react";
import { AiRun, api, ItemStat, Sentence, settle } from "./api";

// Every number the AI states comes from the server's own statistics; a
// sentence where the model wrote a figure of its own is shown but marked, so
// nothing invented can pass for a fact.
export function Sentences({ items }: { items: Sentence[] }) {
  return (
    <>
      {items.map((s, i) => (
        <span key={i} className={s.verified ? "" : "unverified"} title={s.verified ? "" : "這句的數字不是系統算的，未經驗證"}>
          {s.text}
          {!s.verified && <sup className="uv">未驗證</sup>}
        </span>
      ))}
    </>
  );
}

function useAi() {
  const [status, setStatus] = useState<{ configured: boolean; model: string } | null>(null);
  useEffect(() => {
    api.aiStatus().then(setStatus).catch(() => setStatus({ configured: false, model: "" }));
  }, []);
  return status;
}

function RunView({ run, render }: { run: AiRun | null; render: (answer: any) => JSX.Element }) {
  if (!run) return null;
  if (run.status === "pending" || run.status === "running") return <div className="note">AI 思考中…（通常 10–30 秒）</div>;
  if (run.status === "failed") return <div className="err">{run.error ?? "AI 沒有回答"}</div>;
  return render(run.answer);
}

async function go(start: () => Promise<AiRun>, set: (r: AiRun | null) => void, fail: (m: string) => void) {
  set(null);
  try {
    const first = await start();
    set(first);
    set(await settle(first, set));
  } catch (e) {
    fail(e instanceof Error ? e.message : "AI 沒有回答");
  }
}

export default function AiPanel({ examUuid, item }: { examUuid: string; item: ItemStat }) {
  const status = useAi();
  const [run, setRun] = useState<AiRun | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { setRun(null); setError(""); }, [item.question_no, examUuid]);

  if (status && !status.configured) {
    return (
      <div className="card">
        <h2>AI 解釋</h2>
        <div className="note">伺服器尚未設定 AI 金鑰。</div>
      </div>
    );
  }
  return (
    <div className="card">
      <h2>AI 解釋 <span>第 {item.question_no} 題</span></h2>
      {!run && !error && (
        <button className="ghost" onClick={() => go(() => api.explain(examUuid, item.question_no), setRun, setError)}>
          為什麼大家這樣答？
        </button>
      )}
      {error && <div className="err">{error}</div>}
      <RunView run={run} render={(a) => (
        <div className="ai">
          {a.key_check && <div className="callout">建議先確認這題的標準答案有沒有設錯。</div>}
          <p><b>考什麼：</b><Sentences items={a.concept} /></p>
          <p><b>為什麼：</b><Sentences items={a.why} /></p>
          <p><b>下堂課：</b><Sentences items={a.suggestion} /></p>
          {!a.saw_question && <div className="note">這題的題目區塊讀不到，解釋只根據作答數字。</div>}
        </div>
      )} />
    </div>
  );
}

export function ExamAi({ examUuid }: { examUuid: string }) {
  const status = useAi();
  const [summary, setSummary] = useState<AiRun | null>(null);
  const [answer, setAnswer] = useState<AiRun | null>(null);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  if (!status?.configured) return null;
  return (
    <div className="card">
      <h2>AI 助理 <span>{status.model}</span></h2>
      {!summary ? (
        <button className="ghost" onClick={() => go(() => api.summary(examUuid), setSummary, setError)}>產生考試摘要</button>
      ) : (
        <RunView run={summary} render={(a) => (
          <div className="ai">
            <p><Sentences items={a.summary} /></p>
            {a.focus?.length > 0 && <ul>{a.focus.map((f: Sentence[], i: number) => <li key={i}><Sentences items={f} /></li>)}</ul>}
            <div className="note">AI 草稿，分享前請先看過。</div>
          </div>
        )} />
      )}
      <form className="askrow" onSubmit={(e) => { e.preventDefault(); if (question.trim().length > 1) go(() => api.ask(examUuid, question.trim()), setAnswer, setError); }}>
        <input id="ask" value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="問這次考試，例如：哪些學生需要注意？" maxLength={300} />
        <button className="ghost" type="submit">問</button>
      </form>
      {error && <div className="err">{error}</div>}
      <RunView run={answer} render={(a) => <div className="ai"><p><Sentences items={a.answer} /></p></div>} />
    </div>
  );
}
