import { ApiError, signOut, token } from "../api";

// The editor needs raw responses (blobs, multipart uploads), so it gets its own
// fetch on the report's token and error shape rather than the JSON helper.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const t = token();
  if (t) headers.set("Authorization", `Bearer ${t}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && t) signOut();
  if (!res.ok) {
    let detail = `伺服器回應 ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      // Validation errors arrive as a list; the first one says what to fix.
      else if (Array.isArray(body.detail) && typeof body.detail[0]?.msg === "string")
        detail = body.detail[0].msg.replace(/^Value error, /, "");
    } catch { /* not JSON */ }
    if (res.status === 412) detail = "別人剛改過，請重新載入";
    throw new ApiError(res.status, detail);
  }
  return res;
}
