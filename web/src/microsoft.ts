// Microsoft sign-in for the class report.
//
// The same authorization-code-with-PKCE flow the phone runs
// (MicrosoftSignIn.swift), done in the browser because a single-page
// application's code can only be redeemed from one. Microsoft sends the
// browser back to /web/ with a code; this file trades it for an ID token and
// the caller hands that to our API, which checks it exactly as it checks the
// phone's. No library: the flow is two requests, and every step is here to read.

import { ApiError } from "./api";

export type MicrosoftConfig = { enabled: boolean; tenant_id?: string | null; client_id?: string | null };

type Pending = { verifier: string; state: string; nonce: string; tenant: string; client: string };

const PENDING_KEY = "fudao.microsoftPending";
const SCOPE = "openid profile email";

// Must match, character for character, the address added to the school's app
// registration: https://<host>[:port]/web/
function redirectUri(): string {
  return `${location.origin}/web/`;
}

// Hashing for PKCE needs WebCrypto, which browsers only offer on https. On the
// building's plain-http address the button is hidden and the code still works.
export function microsoftAvailable(): boolean {
  return window.isSecureContext && typeof crypto !== "undefined" && !!crypto.subtle;
}

function base64url(bytes: Uint8Array): string {
  let text = "";
  bytes.forEach((b) => { text += String.fromCharCode(b); });
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function random(bytes: number): string {
  return base64url(crypto.getRandomValues(new Uint8Array(bytes)));
}

async function challengeFor(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64url(new Uint8Array(digest));
}

function endpoint(tenant: string, path: "authorize" | "token"): string {
  return `https://login.microsoftonline.com/${encodeURIComponent(tenant)}/oauth2/v2.0/${path}`;
}

export async function startMicrosoftSignIn(config: MicrosoftConfig): Promise<void> {
  if (!config.enabled || !config.tenant_id || !config.client_id) {
    throw new ApiError(0, "網頁尚未開放 Microsoft 登入");
  }
  const pending: Pending = {
    verifier: random(48),
    state: random(16),
    nonce: random(16),
    tenant: config.tenant_id,
    client: config.client_id,
  };
  try {
    sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  } catch {
    throw new ApiError(0, "瀏覽器不允許儲存登入狀態，請關閉無痕模式再試一次");
  }
  const url = new URL(endpoint(pending.tenant, "authorize"));
  url.search = new URLSearchParams({
    client_id: pending.client,
    response_type: "code",
    response_mode: "query",
    redirect_uri: redirectUri(),
    scope: SCOPE,
    state: pending.state,
    nonce: pending.nonce,
    code_challenge: await challengeFor(pending.verifier),
    code_challenge_method: "S256",
    // Shared school computers remember the last person's Microsoft session;
    // asking every time keeps one teacher from landing in another's account.
    prompt: "select_account",
  }).toString();
  location.assign(url.toString());
}

function takePending(): Pending | null {
  try {
    const raw = sessionStorage.getItem(PENDING_KEY);
    sessionStorage.removeItem(PENDING_KEY);
    return raw ? (JSON.parse(raw) as Pending) : null;
  } catch {
    return null;
  }
}

function nonceIn(idToken: string): string | undefined {
  try {
    const payload = idToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(
      Array.from(atob(payload), (c) => `%${c.charCodeAt(0).toString(16).padStart(2, "0")}`).join(""),
    );
    return JSON.parse(json).nonce;
  } catch {
    return undefined;
  }
}

function failure(error: string | null | undefined): ApiError {
  if (error === "access_denied") return new ApiError(0, "已取消 Microsoft 登入");
  return new ApiError(0, `Microsoft 登入失敗${error ? `（${error}）` : ""}，請再試一次或改用登入碼`);
}

async function finish(): Promise<string | null> {
  const params = new URLSearchParams(location.search);
  const code = params.get("code");
  const error = params.get("error");
  if (!code && !error) return null;

  // A code works once and an error should not come back on reload, so the
  // address bar is cleaned before anything else can fail.
  history.replaceState(null, "", `${redirectUri()}${location.hash}`);
  const pending = takePending();

  if (error) throw failure(error);
  if (!pending || params.get("state") !== pending.state) {
    throw new ApiError(0, "登入流程已過期，請再按一次「使用機構 Microsoft 帳號登入」");
  }

  const res = await fetch(endpoint(pending.tenant, "token"), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: pending.client,
      grant_type: "authorization_code",
      code: code!,
      redirect_uri: redirectUri(),
      code_verifier: pending.verifier,
      scope: SCOPE,
    }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || typeof body.id_token !== "string") throw failure(body.error);

  // The nonce ties this token to the sign-in this tab started; a token
  // injected from anywhere else carries a different one.
  if (nonceIn(body.id_token) !== pending.nonce) {
    throw new ApiError(0, "Microsoft 回傳的登入資訊不符，請重新登入");
  }
  return body.id_token;
}

// Once per page load. React's StrictMode runs effects twice in development,
// and the code in the address bar can be redeemed only once.
let answer: Promise<string | null> | undefined;
export function microsoftAnswer(): Promise<string | null> {
  answer ??= finish();
  return answer;
}

export function isMicrosoftAnswer(): boolean {
  const params = new URLSearchParams(location.search);
  return params.has("code") || params.has("error");
}
