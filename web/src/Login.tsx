import { BRAND } from "./brand";
import { useEffect, useRef, useState } from "react";
import { microsoftConfig, microsoftWebLogin, webLogin } from "./api";
import {
  isMicrosoftAnswer,
  microsoftAnswer,
  microsoftAvailable,
  MicrosoftConfig,
  startMicrosoftSignIn,
} from "./microsoft";

export default function Login({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // True while this page load is Microsoft sending the browser back.
  const [returning, setReturning] = useState(isMicrosoftAnswer);
  const [microsoft, setMicrosoft] = useState<MicrosoftConfig | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const idToken = await microsoftAnswer();
        if (cancelled) return;
        if (idToken) {
          await microsoftWebLogin(idToken);
          if (!cancelled) done.current();
          return;
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "登入失敗");
      }
      if (cancelled) return;
      setReturning(false);
      microsoftConfig()
        .then((cfg) => { if (!cancelled) setMicrosoft(cfg); })
        .catch(() => { /* the code sign-in below still works */ });
    })();
    return () => { cancelled = true; };
  }, []);

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

  async function signInWithMicrosoft() {
    if (!microsoft) return;
    setBusy(true);
    setError("");
    try {
      await startMicrosoftSignIn(microsoft); // leaves the page on success
    } catch (err) {
      setError(err instanceof Error ? err.message : "登入失敗");
      setBusy(false);
    }
  }

  const offerMicrosoft = !!microsoft?.enabled && microsoftAvailable();

  return (
    <div className="login">
      <form onSubmit={submit}>
        {BRAND === "浮島" ? <img src="/web/fudao-mark.png" alt={BRAND} /> : <span className="brand-mark" aria-label={BRAND}>{BRAND.slice(0, 1)}</span>}
        <h1 style={{ fontSize: 26, fontWeight: 700 }}>{BRAND}</h1>
        <span className="note">班級報告</span>
        {returning ? (
          <p className="note" style={{ marginTop: 14 }}>正在以 Microsoft 帳號登入…</p>
        ) : (
          <>
            {offerMicrosoft && (
              <>
                <button type="button" className="btn primary" style={{ marginTop: 14 }}
                  disabled={busy} onClick={signInWithMicrosoft}>
                  使用機構 Microsoft 帳號登入
                </button>
                <span className="note" style={{ marginTop: 6 }}>或輸入手機上的登入碼</span>
              </>
            )}
            <label htmlFor="code" className="caption" style={{ marginTop: offerMicrosoft ? 4 : 14, alignSelf: "stretch" }}>登入碼</label>
            <input id="code" className="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} placeholder="000000"
              value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} autoFocus={!offerMicrosoft} />
          </>
        )}
        <div className="err" style={{ minHeight: 20 }}>{error}</div>
        {!returning && (
          <>
            <button className={offerMicrosoft ? "btn ghost" : "btn primary"} disabled={code.length !== 6 || busy}>
              {busy ? "登入中…" : offerMicrosoft ? "以登入碼登入" : "登入"}
            </button>
            <p className="note" style={{ textAlign: "center" }}>在手機 App 的「設定 → 在電腦上看報告」取得 6 位數登入碼。</p>
          </>
        )}
      </form>
    </div>
  );
}
