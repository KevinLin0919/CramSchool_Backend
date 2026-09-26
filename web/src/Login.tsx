import { useState } from "react";
import { webLogin } from "./api";

export default function Login({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await webLogin(code);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <img src="/web/fudao-mark.png" alt="浮島" />
        <h1 style={{ fontSize: 26 }}>浮島</h1>
        <span className="note">班級報告</span>
        <label htmlFor="code" className="caption" style={{ marginTop: 14, alignSelf: "stretch" }}>登入碼</label>
        <input id="code" className="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000"
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} autoFocus />
        <div className="err" style={{ minHeight: 20 }}>{error}</div>
        <button className="btn primary" disabled={code.length !== 6 || busy}>{busy ? "登入中…" : "登入"}</button>
        <p className="note" style={{ textAlign: "center" }}>在手機 App 的「設定 → 在電腦上看報告」取得 6 位數登入碼。</p>
      </form>
    </div>
  );
}
