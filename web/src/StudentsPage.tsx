import { useEffect, useMemo, useState } from "react";
import { api, ClassRoster, Trend } from "./api";
import { go, pct } from "./App";
import { Sparkline } from "./charts";

type Row = {
  id: number; name: string; rates: number[]; last: number | null; mean: number | null;
  watch: string | null; lastUnit: string | null;
};

// The same line the exam report's 需要關注 draws: well under the student's
// own usual, or under half on the latest paper.
function watchReason(rates: number[]): string | null {
  const last = rates[rates.length - 1];
  if (last === undefined) return null;
  const before = rates.slice(0, -1);
  if (before.length) {
    const usual = before.reduce((a, r) => a + r, 0) / before.length;
    if (usual - last >= 0.15) return `比平常低 ${Math.round((usual - last) * 100)}%`;
  }
  return last < 0.5 ? "最近一次未過半" : null;
}

const SORTS = [
  { key: "watch", text: "需要關注優先" },
  { key: "last", text: "最近一次" },
  { key: "name", text: "姓名" },
] as const;

// 學生: everyone in one class, so a teacher picks a student rather than
// searching for one.
export default function StudentsPage({ classId }: { classId?: number }) {
  const [classes, setClasses] = useState<ClassRoster[] | null>(null);
  const [trend, setTrend] = useState<Trend | null>(null);
  const [sort, setSort] = useState<(typeof SORTS)[number]["key"]>("watch");
  const [error, setError] = useState("");

  useEffect(() => { api.classes().then(setClasses).catch((e) => setError(e.message)); }, []);
  const current = classes?.find((c) => c.id === classId) ?? classes?.[0];
  useEffect(() => {
    if (!current) return;
    setTrend(null);
    api.trend(current.id).then(setTrend).catch((e) => setError(e.message));
  }, [current?.id]);

  const rows = useMemo<Row[]>(() => {
    if (!current) return [];
    const byId = new Map(trend?.students.map((s) => [s.student_id, s]) ?? []);
    const order = new Map(trend?.exams.map((e, i) => [e.exam_uuid, i]) ?? []);
    const list = current.students.map((st) => {
      const results = [...(byId.get(st.id)?.results ?? [])].sort((a, b) => (order.get(a.exam_uuid) ?? 0) - (order.get(b.exam_uuid) ?? 0));
      const rates = results.map((r) => r.rate);
      return {
        id: st.id, name: st.name, rates,
        last: rates.length ? rates[rates.length - 1] : null,
        mean: rates.length ? rates.reduce((a, r) => a + r, 0) / rates.length : null,
        watch: watchReason(rates), lastUnit: results[results.length - 1]?.unit ?? null,
      };
    });
    const byName = (a: Row, b: Row) => a.name.localeCompare(b.name, "zh-Hant");
    return list.sort(sort === "name" ? byName
      : sort === "last" ? (a, b) => (b.last ?? -1) - (a.last ?? -1) || byName(a, b)
      : (a, b) => Number(!!b.watch) - Number(!!a.watch) || (a.last ?? 2) - (b.last ?? 2) || byName(a, b));
  }, [current, trend, sort]);

  if (error) return <div className="card empty">{error}</div>;
  if (!classes) return <div className="empty">載入中…</div>;
  if (!current) return <div className="card empty">還沒有班級。在 App 建立班級與名冊後，學生會出現在這裡。</div>;

  const watching = rows.filter((r) => r.watch).length;
  const lastUnit = trend?.exams[trend.exams.length - 1]?.unit;
  const cols = "minmax(0,1.3fr) minmax(0,.8fr) minmax(0,.8fr) 150px minmax(0,1.1fr)";

  return (
    <>
      <div className="head">
        <div>
          <span className="crumb">學生</span>
          <h1>{current.name}</h1>
          <span className="meta">{current.students.length} 位學生{trend && <><span className="dot">·</span>{trend.exams.length} 次考試</>}{watching > 0 && <><span className="dot">·</span><span style={{ color: "var(--bad-d)", fontWeight: 700 }}>{watching} 位需要關注</span></>}</span>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          {classes.length > 1 && (
            <div className="seg" role="group" aria-label="班級">
              {classes.map((c) => <button key={c.id} type="button" className={c.id === current.id ? "on" : ""} onClick={() => go(`/students/${c.id}`)}>{c.name}</button>)}
            </div>
          )}
          <div className="seg" role="group" aria-label="排序">
            {SORTS.map((s) => <button key={s.key} type="button" className={sort === s.key ? "on" : ""} onClick={() => setSort(s.key)}>{s.text}</button>)}
          </div>
        </div>
      </div>

      <section className="card">
        <div className="table">
          <div className="tr th" style={{ gridTemplateColumns: cols }}>
            <span>學生</span><span className="n">最近一次{lastUnit ? `（${lastUnit}）` : ""}</span><span className="n">平均</span><span>趨勢</span><span>狀態</span>
          </div>
          {rows.map((r) => (
            <button key={r.id} type="button" className="tr" style={{ gridTemplateColumns: cols, padding: "10px 12px" }} onClick={() => go(`/student/${r.id}`)}>
              <span style={{ fontWeight: 700 }}>{r.name}</span>
              <span className="n" style={{ color: r.last !== null && r.last < 0.5 ? "var(--bad-d)" : undefined, fontWeight: 700 }}>
                {pct(r.last)}{r.lastUnit && r.lastUnit !== lastUnit && <small>{r.lastUnit}</small>}
              </span>
              <span className="n">{pct(r.mean)}</span>
              <span>{r.rates.length >= 2 ? <Sparkline values={r.rates} /> : <span className="note">{r.rates.length ? "只有一次" : "—"}</span>}</span>
              <span>{r.watch ? <span className="pill bad">{r.watch}</span> : !r.rates.length && <span className="pill muted">尚無考卷</span>}</span>
            </button>
          ))}
        </div>
      </section>
    </>
  );
}
