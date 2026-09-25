// Same-origin API client. The web token is a 12-hour credential minted from
// a six-digit code on the phone; it lives in sessionStorage so closing the
// browser on a shared school computer ends the session.

const TOKEN_KEY = "fudao.webToken";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function token(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function signOut() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: nothing to clear */
  }
  location.hash = "";
  location.reload();
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...init, headers: { ...headers, ...(init.headers ?? {}) } });
  if (res.status === 401 && t) {
    signOut();
  }
  if (!res.ok) {
    let detail = `伺服器回應 ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return res.status === 204 ? (undefined as T) : res.json();
}

export async function webLogin(code: string) {
  const out = await request<{ token: string; teacher_name: string }>("/api/v1/auth/web-login", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
  try {
    sessionStorage.setItem(TOKEN_KEY, out.token);
  } catch {
    throw new ApiError(0, "瀏覽器不允許儲存登入狀態，請關閉無痕模式再試一次");
  }
  return out;
}

export type Me = { id: number; name: string; role: string };
export type Exam = {
  client_uuid: string;
  class_id: number;
  class_name: string;
  template_id: number;
  template_name: string;
  unit: string | null;
  exam_date: string;
  sitting: number;
  is_simulated: boolean;
  paper_count: number;
  identified_count: number;
};

export type ItemStat = {
  question_no: number;
  answer_type: "choice" | "mark";
  key: string;
  papers: number;
  answered: number;
  correct: number;
  wrong: number;
  blank: number;
  pending: number;
  correct_rate: number | null;
  options: Record<string, number>;
  invalid: number;
  top_wrong: { option: string; count: number } | null;
  unchosen: string[];
  discrimination: number | null;
  high_low: { high_n: number; low_n: number; high: Record<string, number>; low: Record<string, number> } | null;
  flags: string[];
};

export type Report = {
  exam: {
    uuid: string;
    class_id: number;
    class_name: string;
    is_simulated: boolean;
    template_id: number;
    template_name: string;
    unit: string | null;
    exam_date: string;
    sitting: number;
  };
  papers: number;
  identified: number;
  total: number;
  small_group: boolean;
  mean: number | null;
  median: number | null;
  pending_cells: number;
  distribution: { correct: number; papers: number }[];
  choice: { correct: number; total: number };
  mark: { correct: number; total: number };
  items: ItemStat[];
  paper_list: { session_uuid: string; student_id: number | null; student_name: string | null; correct: number; pending: number }[];
};

export type ItemStudents = {
  question_no: number;
  key: string;
  groups: Record<string, { session_uuid: string; student_name: string | null }[]>;
};

export type Trend = {
  exams: { exam_uuid: string; unit: string | null; template_name: string; exam_date: string; papers: number; mean_rate: number; choice_rate: number | null; mark_rate: number | null }[];
  students: { student_id: number; student_name: string | null; results: { exam_uuid: string; unit: string | null; rate: number; choice: [number, number]; mark: [number, number] }[] }[];
};

export type Profile = {
  student_id: number;
  student_name: string | null;
  results: { exam_uuid: string; unit: string | null; template_name: string; exam_date: string; correct: number; total: number; pending: number; choice: [number, number]; mark: [number, number]; wrong: { question_no: number; chosen: string; key: string }[] }[];
};

export type Sentence = { text: string; verified: boolean };
export type AiRun = {
  id: number;
  kind: string;
  status: "pending" | "running" | "done" | "failed";
  error: string | null;
  answer: any;
  model: string | null;
  cost_usd: number | null;
};

export const api = {
  me: () => request<Me>("/api/v1/auth/me"),
  exams: () => request<Exam[]>("/api/v1/exams"),
  report: (uuid: string) => request<Report>(`/api/v1/exams/${uuid}/report`),
  itemStudents: (uuid: string, q: number) => request<ItemStudents>(`/api/v1/exams/${uuid}/items/${q}/students`),
  trend: (classId: number) => request<Trend>(`/api/v1/classes/${classId}/trend`),
  profile: (studentId: number) => request<Profile>(`/api/v1/students/${studentId}/profile`),
  aiStatus: () => request<{ configured: boolean; model: string }>("/api/v1/ai/status"),
  explain: (uuid: string, q: number) => request<AiRun>(`/api/v1/ai/exams/${uuid}/items/${q}/explain`, { method: "POST" }),
  summary: (uuid: string) => request<AiRun>(`/api/v1/ai/exams/${uuid}/summary`, { method: "POST" }),
  ask: (uuid: string, question: string) => request<AiRun>(`/api/v1/ai/exams/${uuid}/ask`, { method: "POST", body: JSON.stringify({ question }) }),
  run: (id: number) => request<AiRun>(`/api/v1/ai/runs/${id}`),
};

/** Polls a run until it settles. The model can take tens of seconds. */
export async function settle(run: AiRun, onTick?: (r: AiRun) => void): Promise<AiRun> {
  let current = run;
  for (let i = 0; i < 90 && (current.status === "pending" || current.status === "running"); i++) {
    await new Promise((r) => setTimeout(r, 1500));
    current = await api.run(current.id);
    onTick?.(current);
  }
  return current;
}
