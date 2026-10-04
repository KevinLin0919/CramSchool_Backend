import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Check, ChevronLeft, ChevronRight, Eye, FileText, Pencil, Search, Upload, X } from "lucide-react";
import { go } from "../App";
import { normalizeImage } from "./imaging";
import { deleteTemplate, listTemplates, masterBlob, pdfPages, renameTemplate, type SourcePage, type TemplateSummary } from "./templates";
import { getDraft, setDraft } from "./draft";
import { askConfirm, showToast } from "./feedback";

// 模板: one page, two jobs. 上傳模板 starts a paper from its answer key — photos
// or a PDF, one page or several — and 編輯模板 is every saved paper, to open,
// preview, rename or retire. Students' papers are the phone's job.
export default function TemplatesPage({ tab }: { tab: "upload" | "list" }) {
  return (
    <div className="tpl">
      <div className="upload-container">
        <h1 className="ds-page-title">模板</h1>
        <p className="ds-page-desc page-desc">上傳標準答案卷建立新模板，或打開已儲存的模板修改；學生考卷請使用 App 掃描。</p>
        <div className="ds-segmented hub-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === "upload"} className={`ds-segmented__btn ${tab === "upload" ? "is-active" : ""}`} onClick={() => go("/templates")}>
            <Upload size={14} /> 上傳模板
          </button>
          <button type="button" role="tab" aria-selected={tab === "list"} className={`ds-segmented__btn ${tab === "list" ? "is-active" : ""}`} onClick={() => go("/templates/list")}>
            <Pencil size={14} /> 編輯模板
          </button>
        </div>
        {tab === "upload" ? <UploadPanel /> : <ListPanel />}
      </div>
    </div>
  );
}

// More pages than this and the upload is probably a whole stack of papers, so
// nothing is ticked and the teacher picks this paper's sides.
const PRESELECT_UP_TO = 4;

type Candidate = SourcePage & { key: string };

const isPdf = (file: File) => file.type === "application/pdf" || /\.pdf$/i.test(file.name);

function UploadPanel() {
  const input = useRef<HTMLInputElement>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [examName, setExamName] = useState("");
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState("");
  const live = useRef<Candidate[]>([]);
  live.current = candidates;
  const nextKey = useRef(0);

  // A half-made paper from an earlier visit is reopened, not lost.
  const resumable = getDraft();
  const canResume = !!resumable && !resumable.id;

  // Previews not taken into a draft are freed on the way out.
  useEffect(() => () => {
    const kept = new Set(getDraft()?.pages.map((p) => p.preview) ?? []);
    live.current.forEach((c) => { if (!kept.has(c.preview)) URL.revokeObjectURL(c.preview); });
  }, []);

  const addFiles = async (files: File[]) => {
    if (processing) return;
    const usable = files.filter((f) => f.type.startsWith("image/") || isPdf(f));
    if (files.length > usable.length) showToast(`已略過 ${files.length - usable.length} 個不是圖片或 PDF 的檔案`, "info");
    if (!usable.length) return;
    usable.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
    const added: Candidate[] = [];
    try {
      for (const [i, file] of usable.entries()) {
        setProcessing(usable.length > 1 ? `處理第 ${i + 1}/${usable.length} 個檔案…` : isPdf(file) ? "PDF 轉換中…" : "處理中…");
        if (isPdf(file)) {
          (await pdfPages(file)).forEach((p) => added.push({ ...p, key: `k${nextKey.current++}` }));
        } else {
          const n = await normalizeImage(file);
          added.push({ source: file.name, pageNo: 1, ...n, key: `k${nextKey.current++}` });
        }
      }
    } catch (error) {
      showToast(error instanceof Error ? error.message : "檔案處理失敗，請換一個再試", "error");
    } finally { setProcessing(""); }
    if (!added.length) return;
    const all = [...candidates, ...added];
    setCandidates(all);
    if (all.length <= PRESELECT_UP_TO) setChosen(all.map((c) => c.key));
    if (!examName) setExamName(usable[0]!.name.replace(/\.[^.]+$/, ""));
  };

  const clearAll = () => {
    if (processing) return;
    candidates.forEach((c) => URL.revokeObjectURL(c.preview));
    setCandidates([]);
    setChosen([]);
    setExamName("");
  };

  // Ticking order is page order: the first ticked becomes 第 1 面.
  const toggle = (key: string) => setChosen((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]));
  const selected = chosen.map((k) => candidates.find((c) => c.key === k)).filter((c): c is Candidate => !!c);

  const start = async () => {
    if (processing) return;
    if (!selected.length) { showToast("請勾選這份考卷用到的頁面", "error"); return; }
    if (!examName.trim()) { showToast("請輸入考卷名稱後再繼續", "error"); return; }
    if (canResume && !await askConfirm({ title: "開始新模板", message: "上次未完成的模板會被捨棄，確定繼續嗎？", confirmText: "開始新模板", danger: true })) return;
    setDraft({
      name: examName.trim(), unit: "", optionCount: 4, nameBoxDirty: false, maxQuestionNo: 0,
      pages: selected.map((c, i) => ({ pageIndex: i, width: c.width, height: c.height, preview: c.preview, blob: c.blob, labels: [] })),
    });
    go("/templates/edit");
  };

  const pageName = (c: Candidate) => (/\.pdf$/i.test(c.source) ? `第 ${c.pageNo} 頁` : c.source);

  return (
    <div className="upload-area">
      {canResume && (
        <div className="ds-card resume-card">
          <span>有一份尚未儲存的模板「{resumable!.name}」（{resumable!.pages.length} 面）</span>
          <button className="ds-btn ds-btn--primary ds-btn--sm" onClick={() => go("/templates/edit")}>繼續標註</button>
        </div>
      )}
      <section className="upload-section">
        <h2 className="ds-section-title section-title">標準答案卷</h2>
        <div
          className={`ds-dropzone ${candidates.length ? "ds-dropzone--compact" : ""} ${dragging ? "is-dragover" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
          onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(Array.from(e.dataTransfer.files)); }}
          onClick={() => input.current?.click()}
        >
          <span className="ds-dropzone__icon"><Upload size={18} /></span>
          <p>{processing || "拖曳或點擊上傳標準答案卷：圖片或 PDF，可一次多頁（例如正反面）"}</p>
          <input type="file" ref={input} accept="image/*,application/pdf,.pdf" multiple style={{ display: "none" }}
            onChange={(e) => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
          <button className="ds-btn ds-btn--sm" disabled={!!processing} onClick={(e) => { e.stopPropagation(); input.current?.click(); }}>
            {candidates.length ? "再加入檔案" : "選擇檔案"}
          </button>
        </div>

        {candidates.length > 0 && (
          <div className="ds-card page-picker">
            <div className="filename-row">
              <FileText size={15} className="file-ic" />
              <span className="file-name">
                {!selected.length
                  ? `共 ${candidates.length} 頁，請依序點選這份考卷用到的頁面`
                  : `已選 ${selected.length} 頁；點選的順序就是第 1、2…面`}
              </span>
              <button disabled={!!processing} onClick={clearAll} className="ds-btn ds-btn--danger ds-btn--sm">清除全部</button>
            </div>
            <input type="text" value={examName} onChange={(e) => setExamName(e.target.value)} placeholder="請輸入考卷名稱" className="ds-input" />
            <div className="page-grid">
              {candidates.map((c) => {
                const order = chosen.indexOf(c.key);
                return (
                  <button type="button" key={c.key} className={`page-thumb ${order >= 0 ? "is-selected" : ""}`} onClick={() => toggle(c.key)}
                    aria-pressed={order >= 0} title={`${c.source}・${pageName(c)}`}>
                    <img src={c.preview} alt={pageName(c)} />
                    <span className="page-thumb__label">{pageName(c)}</span>
                    {order >= 0 && <span className="page-thumb__order">第 {order + 1} 面</span>}
                  </button>
                );
              })}
            </div>
            <div className="action-buttons">
              <button onClick={() => void start()} disabled={!!processing || !selected.length} className="ds-btn ds-btn--primary">
                <Upload size={16} /> 上傳並標註{selected.length > 1 ? `（${selected.length} 面）` : ""}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function ListPanel() {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [preview, setPreview] = useState<{ template: TemplateSummary; page: number; url: string } | null>(null);
  const listRequest = useRef(0);
  const previewRequest = useRef(0);

  const load = async (search = "") => {
    const request = ++listRequest.current;
    setLoading(true);
    setError("");
    try {
      const rows = await listTemplates(search);
      if (request === listRequest.current) setTemplates(rows);
    } catch (e) {
      if (request !== listRequest.current) return;
      setTemplates([]);
      setError(e instanceof Error ? e.message : "載入模板失敗");
    } finally {
      if (request === listRequest.current) setLoading(false);
    }
  };

  useEffect(() => () => { listRequest.current++; previewRequest.current++; }, []);
  useEffect(() => { const t = setTimeout(() => void load(query), query ? 300 : 0); return () => clearTimeout(t); }, [query]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setPreview(null); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const confirmEdit = async (t: TemplateSummary) => {
    const name = editingName.trim();
    if (name && name !== t.exam_name) {
      try {
        await renameTemplate(t, name);
        setTemplates((rows) => rows.map((r) => (r.id === t.id ? { ...t } : r)));
      } catch (e) {
        showToast(e instanceof Error ? e.message : "改名失敗，請稍後再試", "error");
      }
    }
    setEditingId(null);
  };

  const remove = async (t: TemplateSummary) => {
    if (!await askConfirm({ title: "刪除模板", message: `確定要刪除「${t.exam_name}」嗎？已批改的考卷會保留。`, confirmText: "刪除", danger: true })) return;
    try {
      await deleteTemplate(t.id);
      setTemplates((rows) => rows.filter((r) => r.id !== t.id));
      showToast("已刪除模板", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "刪除失敗，請稍後再試", "error");
    }
  };

  const showPreview = async (template: TemplateSummary, page = 0) => {
    const request = ++previewRequest.current;
    try {
      const blob = await masterBlob(template.id, 1600, page);
      if (request === previewRequest.current) setPreview({ template, page, url: URL.createObjectURL(blob) });
    } catch (e) {
      showToast(e instanceof Error ? e.message : "預覽載入失敗", "error");
    }
  };

  return (
    <section className="upload-section list-panel">
      <div className="ds-input-group list-search">
        <Search size={14} />
        <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜尋模板名稱…" className="ds-input ds-input--sm" />
      </div>
      {loading ? (
        <div className="modal-status"><span className="ds-spinner"></span><span>載入中…</span></div>
      ) : error ? (
        <div className="modal-status modal-status--error">
          <AlertCircle size={16} /><span>{error}</span>
          <button className="ds-btn ds-btn--sm" onClick={() => void load(query)}>重試</button>
        </div>
      ) : templates.length === 0 ? (
        <div className="modal-status">{query ? "找不到符合的模板" : "尚無儲存的模板"}</div>
      ) : (
        <div className="template-list">
          {templates.map((t) => (
            <div key={t.id} className="template-item">
              <div className="template-info">
                {editingId !== t.id ? (
                  <div className="template-name-row">
                    <span className="template-name">{t.exam_name}</span>
                    <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" onClick={() => { setEditingId(t.id); setEditingName(t.exam_name); }} title="改名">
                      <Pencil size={13} />
                    </button>
                  </div>
                ) : (
                  <div className="template-edit-row">
                    <input className="template-name-input ds-input ds-input--sm" autoFocus value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") void confirmEdit(t); if (e.key === "Escape") { e.stopPropagation(); setEditingId(null); } }} />
                    <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon confirm-icon" onClick={() => void confirmEdit(t)} title="確認"><Check size={14} /></button>
                    <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon cancel-icon" onClick={() => setEditingId(null)} title="取消"><X size={14} /></button>
                  </div>
                )}
                <p className="template-meta">{t.page_count > 1 ? `${t.page_count} 面・` : ""}{t.annotation_count} 格答案區・{t.created_at.slice(0, 10).replace(/-/g, "/")}</p>
              </div>
              <div className="template-actions">
                <button className="ds-btn ds-btn--primary ds-btn--sm" onClick={() => go(`/templates/${t.id}`)}>編輯</button>
                <button className="ds-btn ds-btn--sm" onClick={() => void showPreview(t)}><Eye size={14} /> 預覽</button>
                <button className="ds-btn ds-btn--danger ds-btn--sm" onClick={() => void remove(t)}>刪除</button>
              </div>
            </div>
          ))}
        </div>
      )}
      {preview && (
        <div className="ds-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setPreview(null); }}>
          <div className="ds-modal preview-modal">
            <div className="ds-modal__header">
              <h3>{preview.template.exam_name}{preview.template.page_count > 1 ? `・第 ${preview.page + 1} 面` : ""}</h3>
              <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" onClick={() => setPreview(null)} title="關閉"><X size={14} /></button>
            </div>
            <div className="ds-modal__body preview-body">
              <img src={preview.url} className="preview-full-img" alt="模板預覽" />
            </div>
            <div className="preview-nav">
              <button className="ds-btn ds-btn--sm" onClick={() => setPreview(null)}><ArrowLeft size={14} /> 返回清單</button>
              {preview.template.page_count > 1 && (
                <>
                  <button className="ds-btn ds-btn--sm" disabled={preview.page === 0} onClick={() => void showPreview(preview.template, preview.page - 1)}><ChevronLeft size={14} /> 上一面</button>
                  <button className="ds-btn ds-btn--sm" disabled={preview.page >= preview.template.page_count - 1} onClick={() => void showPreview(preview.template, preview.page + 1)}>下一面 <ChevronRight size={14} /></button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
