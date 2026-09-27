import { ref } from 'vue'

const TOKEN_KEY = 'fudao.webToken'
export const BRAND = import.meta.env.VITE_BRAND || '浮島'

export function token(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
export const signedIn = ref(!!token())

export function signOut() {
  try { sessionStorage.removeItem(TOKEN_KEY) } catch { /* storage unavailable */ }
  signedIn.value = false
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const t = token()
  if (t) headers.set('Authorization', `Bearer ${t}`)
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json')
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401) signOut()
  if (!res.ok) {
    let detail = `伺服器回應 ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch { /* non-JSON error */ }
    if (res.status === 412) detail = '別人剛改過，請重新載入'
    throw new ApiError(res.status, detail)
  }
  return res
}

export async function webLogin(code: string) {
  const res = await apiFetch('/api/v1/auth/web-login', {
    method: 'POST', body: JSON.stringify({ code }),
  })
  const out: { token: string } = await res.json()
  try { sessionStorage.setItem(TOKEN_KEY, out.token) } catch {
    throw new ApiError(0, '瀏覽器不允許儲存登入狀態，請關閉無痕模式再試一次')
  }
  signedIn.value = true
}
