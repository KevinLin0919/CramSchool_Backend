import { BRAND } from "./brand";
import { useEffect, useMemo, useState } from "react";
import { api, ClassRoster, Me, signOut, token } from "./api";
import { Icon } from "./icons";
import Login from "./Login";
import OverviewPage from "./OverviewPage";
import ExamList from "./ExamList";
import ExamReport from "./ExamReport";
import StudentPage from "./StudentPage";
import StudentsPage from "./StudentsPage";
import ClassPage from "./ClassPage";
import TemplatesPage from "./label/TemplatesPage";
import TemplateEditor from "./label/TemplateEditor";
import { FeedbackHost } from "./label/feedback";
import "./label/label.css";

// The template editor exists only in builds that ask for it (QAT).
const WITH_TEMPLATES = import.meta.env.VITE_WITH_LABEL === "1";

// Hash routes, because the page is served as static files under /web and a
// hash never reaches the server: #/exam/<uuid>, #/student/<id>, #/class/<id>.
function useRoute() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const on = () => { setHash(location.hash); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const [, kind, id] = hash.replace(/^#/, "").split("/");
  return { kind: kind || "overview", id };
}

export function go(path: string) {
  location.hash = path;
}

export const label = (o: string) => (o === "O" ? "○" : o === "X" ? "✕" : o === "__blank__" ? "空白" : o);
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

function Search({ classes }: { classes: ClassRoster[] }) {
  const [q, setQ] = useState("");
  const hits = useMemo(() => {
    const t = q.trim();
    if (!t) return [];
    return classes.flatMap((c) => c.students.filter((s) => s.name.includes(t)).map((s) => ({ ...s, cls: c.name }))).slice(0, 8);
  }, [q, classes]);
  return (
    <div className="search">
      <label>
        <Icon.search />
        <input id="search" type="search" placeholder="搜尋學生" aria-label="搜尋學生" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {hits.length > 0 && (
        <div className="hits">
          {hits.map((h) => (
            <button key={h.id} type="button" onClick={() => { setQ(""); go(`/student/${h.id}`); }}>
              {h.name} <span className="note">· {h.cls}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [classes, setClasses] = useState<ClassRoster[]>([]);
  const [signedIn, setSignedIn] = useState(!!token());
  const route = useRoute();

  useEffect(() => {
    if (!signedIn) return;
    api.me().then(setMe).catch(() => setSignedIn(false));
    api.classes().then(setClasses).catch(() => setClasses([]));
  }, [signedIn]);

  if (!signedIn) return <Login onDone={() => setSignedIn(true)} />;

  // Templates are shared by every teacher grading that paper, so building and
  // editing them is a template manager's (or an admin's). The API refuses the
  // rest; this only keeps the page from offering it.
  const canTemplates = me?.role === "admin" || me?.role === "template_manager";
  const roleName = me?.role === "admin" ? "管理員" : me?.role === "template_manager" ? "模板管理者" : "老師";

  const nav = [
    { key: "overview", text: "總覽", icon: Icon.overview, path: "/overview" },
    { key: "exams", text: "考試", icon: Icon.exam, path: "/exams", also: ["exam"] },
    { key: "students", text: "學生", icon: Icon.student, path: "/students", also: ["student"] },
    { key: "class", text: "單元趨勢", icon: Icon.trend, path: classes[0] ? `/class/${classes[0].id}` : "/overview" },
  ];

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          {BRAND === "浮島" ? <img src="/web/fudao-mark.png" alt={BRAND} /> : <span className="brand-mark" aria-label={BRAND}>{BRAND.slice(0, 1)}</span>}
          <div><b>{BRAND}</b><span>班級報告</span></div>
        </div>
        <Search classes={classes} />
        <nav className="nav" aria-label="主選單">
          {WITH_TEMPLATES && canTemplates && (
            <button type="button" className={route.kind === "templates" ? "on" : ""} onClick={() => go("/templates")}>
              <Icon.template />模板
            </button>
          )}
          {nav.map((n) => (
            <button key={n.key} type="button" className={route.kind === n.key || n.also?.includes(route.kind) ? "on" : ""} onClick={() => go(n.path)}>
              <n.icon />{n.text}
            </button>
          ))}
        </nav>
        <div className="classes nav">
          <div className="grp">我的班級</div>
          {classes.map((c) => (
            <button key={c.id} type="button" className={`cls ${route.kind === "class" && Number(route.id) === c.id ? "on" : ""}`} onClick={() => go(`/class/${c.id}`)}>
              {c.name}
              <span className="note">{c.students.length} 人</span>
            </button>
          ))}
        </div>
        <div className="me">
          <div className="avatar">{me?.name.slice(0, 1) ?? "·"}</div>
          <div><b style={{ fontSize: 13 }}>{me?.name ?? "載入中"}</b><small>{me ? roleName : ""}</small></div>
          <button type="button" className="linkbtn" onClick={signOut}>登出</button>
        </div>
      </aside>
      <main className="main">
        {WITH_TEMPLATES && route.kind === "templates" && !canTemplates ? (
          <div className="card empty">{me ? "模板由模板管理者維護。需要新增或修改模板，請聯絡模板管理者。" : "載入中…"}</div>
        ) :
         WITH_TEMPLATES && route.kind === "templates" ? (
          route.id === "edit" ? <TemplateEditor key="new" /> :
          route.id && /^\d+$/.test(route.id) ? <TemplateEditor key={route.id} templateId={Number(route.id)} /> :
          <TemplatesPage tab={route.id === "list" ? "list" : "upload"} />
        ) :
         route.kind === "exam" && route.id ? <ExamReport uuid={route.id} /> :
         route.kind === "student" && route.id ? <StudentPage studentId={Number(route.id)} /> :
         route.kind === "students" ? <StudentsPage classId={route.id ? Number(route.id) : undefined} /> :
         route.kind === "class" && route.id ? <ClassPage classId={Number(route.id)} /> :
         route.kind === "exams" ? <ExamList /> :
         <OverviewPage />}
      </main>
      {WITH_TEMPLATES && <div className="tpl"><FeedbackHost /></div>}
    </div>
  );
}
