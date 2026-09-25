import { useEffect, useMemo, useState } from "react";
import { api, Exam, Me, signOut, token } from "./api";
import Login from "./Login";
import ExamList from "./ExamList";
import ExamReport from "./ExamReport";
import StudentPage from "./StudentPage";
import ClassPage from "./ClassPage";

// Hash routes, because the page is served as static files under /web and a
// hash never reaches the server: #/exam/<uuid>, #/student/<id>, #/class/<id>.
function useRoute() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const on = () => setHash(location.hash);
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const [, kind, id] = hash.replace(/^#/, "").split("/");
  return { kind: kind || "exams", id };
}

export function go(path: string) {
  location.hash = path;
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [exams, setExams] = useState<Exam[] | null>(null);
  const [signedIn, setSignedIn] = useState(!!token());
  const route = useRoute();

  useEffect(() => {
    if (!signedIn) return;
    api.me().then(setMe).catch(() => setSignedIn(false));
    api.exams().then(setExams).catch(() => setExams([]));
  }, [signedIn]);

  const classes = useMemo(() => {
    const seen = new Map<number, { id: number; name: string; simulated: boolean }>();
    for (const e of exams ?? []) seen.set(e.class_id, { id: e.class_id, name: e.class_name, simulated: e.is_simulated });
    return [...seen.values()];
  }, [exams]);

  if (!signedIn) return <Login onDone={() => setSignedIn(true)} />;

  return (
    <div className="shell">
      <aside className="side">
        <div className="logo">浮島</div>
        <div className="who">{me ? `${me.name}・班級報告` : "載入中…"}</div>
        <nav className="nav">
          <button className={route.kind === "exams" || route.kind === "exam" ? "on" : ""} onClick={() => go("/exams")}>考試</button>
          <div className="grp">班級</div>
          {classes.map((c) => (
            <button key={c.id} className={route.kind === "class" && Number(route.id) === c.id ? "on" : ""} onClick={() => go(`/class/${c.id}`)}>
              {c.name}
            </button>
          ))}
          <div className="grp">帳號</div>
          <button onClick={signOut}>登出</button>
        </nav>
      </aside>
      <main className="main">
        {route.kind === "exam" && route.id ? <ExamReport uuid={route.id} /> :
         route.kind === "student" && route.id ? <StudentPage studentId={Number(route.id)} /> :
         route.kind === "class" && route.id ? <ClassPage classId={Number(route.id)} /> :
         <ExamList exams={exams} />}
      </main>
    </div>
  );
}
