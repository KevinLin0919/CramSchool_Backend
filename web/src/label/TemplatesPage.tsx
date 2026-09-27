import { useEffect, useRef, useState } from "react";
import { AlertCircle, ArrowLeft, Check, ClipboardList, Eye, FileText, Pencil, Search, Upload, X } from "lucide-react";
import { go } from "../App";
import { normalizeImage } from "./imaging";
import { deleteTemplate, listTemplates, masterBlob, renameTemplate, type TemplateSummary } from "./templates";
import { getDraft, setDraft } from "./draft";
import { showToast } from "./feedback";

// 建立模板: upload a master or pick a saved one. The original editor's upload
// page, less the student-paper half — the phone grades.
export default function TemplatesPage({ openList }: { openList: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const [master, setMaster] = useState<{ name: string; preview: string } | null>(() => {
    const d = getDraft();
    return d && !d.id ? { name: d.name, preview: d.preview } : null;
  });
  const [examName, setExamName] = useState(() => getDraft()?.name ?? "");
  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [modal, setModal] = useState(openList);

  const addFiles = async (files: File[]) => {
    if (processing) return;
    const images = files.filter((f) => f.type.startsWith("image/"));
    if (files.length > images.length) showToast(`已略過 ${files.length - images.length} 個非圖片檔案`, "info");
    const file = images.sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))[0];
    if (!file) return;
    setProcessing(true);
    try {
      const normalized = await normalizeImage(file);
      const name = file.name.replace(/\.[^.]+$/, "");
      setDraft({ ...normalized, name, pageIndex: 0, pageCount: 1, unit: "", optionCount: 4, labels: [], nameBoxDirty: false, maxQuestionNo: 0 });
      setMaster({ name: file.name, preview: normalized.preview });
      setExamName(name);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "圖片處理失敗，請換一張再試", "error");
    } finally { setProcessing(false); }
  };

  const clearAll = () => {
    if (processing) return;
    setDraft(null);
    setMaster(null);
    setExamName("");
  };

  const upload = () => {
    const d = getDraft();
    if (processing || !d || !master) { showToast("請先上傳標準答案卷", "error"); return; }
    if (!examName.trim()) { showToast("請輸入考卷名稱後再繼續", "error"); return; }
    d.name = examName.trim();
    go("/templates/edit");
  };

  return (
    <div className="tpl">
      <div className="upload-container">
        <h1 className="ds-page-title">建立模板</h1>
        <p className="ds-page-desc page-desc">上傳標準答案卷或選擇已儲存模板，再進入標註；學生考卷請使用 App 掃描。</p>

        <div className="upload-area">
          <section className="upload-section">
            <h2 className="ds-section-title section-title">標準答案卷</h2>
            {!master ? (
              <div className="master-input-area">
                <div
                  className={`ds-dropzone ${dragging ? "is-dragover" : ""}`}
                  onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                  onDragLeave={(e) => { e.preventDefault(); setDragging(false); }}
                  onDrop={(e) => { e.preventDefault(); setDragging(false); void addFiles(Array.from(e.dataTransfer.files)); }}
                  onClick={() => input.current?.click()}
                >
                  <span className="ds-dropzone__icon"><Upload size={18} /></span>
                  <p>拖曳或點擊上傳 1 張標準答案卷</p>
                  <input type="file" ref={input} accept="image/*" style={{ display: "none" }}
                    onChange={(e) => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
                  <button className="ds-btn ds-btn--sm" onClick={(e) => { e.stopPropagation(); input.current?.click(); }}>選擇標準答案卷</button>
                </div>
                <div className="or-divider">或</div>
                <div className="ds-dropzone ds-dropzone--accent" onClick={() => setModal(true)}>
                  <span className="ds-dropzone__icon"><ClipboardList size={18} /></span>
                  <p>使用已儲存的答案卷</p>
                  <button className="ds-btn ds-btn--sm" onClick={(e) => { e.stopPropagation(); setModal(true); }}>選擇已儲存答案卷</button>
                </div>
              </div>
            ) : (
              <div className="ds-card master-preview">
                <div className="master-preview-info">
                  <div className="filename-row">
                    <FileText size={15} className="file-ic" />
                    <span className="file-name">{master.name}</span>
                    <button disabled={processing} onClick={clearAll} className="ds-btn ds-btn--danger ds-btn--sm">移除</button>
                  </div>
                  <input type="text" value={examName} onChange={(e) => setExamName(e.target.value)} placeholder="請輸入考卷名稱" className="ds-input" />
                </div>
                <div className="master-preview-figure">
                  <img src={master.preview} alt={master.name} className="master-preview-image" />
                </div>
              </div>
            )}
          </section>
        </div>

        {master && (
          <div className="action-buttons">
            <button disabled={processing} onClick={clearAll} className="ds-btn ds-btn--ghost">清除全部</button>
            <button onClick={upload} disabled={processing} className="ds-btn ds-btn--primary">
              <Upload size={16} /> {processing ? "處理圖片中…" : "上傳並標註"}
            </button>
          </div>
        )}

        {modal && <TemplateModal onClose={() => setModal(false)} />}
      </div>
    </div>
  );
}

function TemplateModal({ onClose }: { onClose: () => void }) {
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState("");
  const [deleting, setDeleting] = useState<TemplateSummary | null>(null);
  const [preview, setPreview] = useState("");
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

  useEffect(() => { void load(); return () => { listRequest.current++; previewRequest.current++; }; }, []);
  useEffect(() => { const t = setTimeout(() => void load(query), 300); return () => clearTimeout(t); }, [query]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  // Esc closes one layer at a time: preview, delete confirm, then the modal.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (preview) setPreview("");
      else if (deleting) setDeleting(null);
      else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [preview, deleting, onClose]);

  const confirmEdit = async (t: TemplateSummary) => {
    const name = editingName.trim();
    if (name) {
      try {
        await renameTemplate(t, name);
        setTemplates((rows) => rows.map((r) => (r.id === t.id ? { ...t } : r)));
      } catch (e) {
        showToast(e instanceof Error ? e.message : "改名失敗，請稍後再試", "error");
      }
    }
    setEditingId(null);
  };

  const remove = async () => {
    if (!deleting) return;
    try {
      await deleteTemplate(deleting.id);
      setTemplates((rows) => rows.filter((r) => r.id !== deleting.id));
      showToast("已刪除模板", "success");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "刪除失敗，請稍後再試", "error");
    }
    setDeleting(null);
  };

  const showPreview = async (id: number) => {
    const request = ++previewRequest.current;
    try {
      const blob = await masterBlob(id, 1600);
      if (request === previewRequest.current) setPreview(URL.createObjectURL(blob));
    } catch (e) {
      showToast(e instanceof Error ? e.message : "預覽載入失敗", "error");
    }
  };

  return (
    <div className="ds-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="ds-modal">
        <div className="ds-modal__header">
          <h3>選擇已儲存的答案卷模板</h3>
          <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" onClick={onClose} title="關閉"><X size={14} /></button>
        </div>
        <div className="modal-search">
          <div className="ds-input-group">
            <Search size={14} />
            <input type="text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜尋模板名稱…" className="ds-input ds-input--sm" />
          </div>
        </div>
        <div className="ds-modal__body">
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
                        <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" disabled={t.page_count > 1}
                          onClick={() => { setEditingId(t.id); setEditingName(t.exam_name); }} title={t.page_count > 1 ? "多頁考卷目前只能檢視" : "改名"}>
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
                    <p className="template-meta">{t.annotation_count} 格答案區・{t.created_at.slice(0, 10).replace(/-/g, "/")}{t.page_count > 1 && <span>・多頁考卷目前只能檢視</span>}</p>
                  </div>
                  <div className="template-actions">
                    <button className="ds-btn ds-btn--primary ds-btn--sm" onClick={() => go(`/templates/${t.id}`)}>{t.page_count > 1 ? "檢視" : "選擇"}</button>
                    <button className="ds-btn ds-btn--sm" onClick={() => void showPreview(t.id)}><Eye size={14} /> 預覽</button>
                    <button className="ds-btn ds-btn--danger ds-btn--sm" onClick={() => setDeleting(t)}>刪除</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        {deleting && (
          <div className="modal-inner-overlay">
            <div className="confirm-box">
              <p>確定要刪除「{deleting.exam_name}」嗎？</p>
              <div className="confirm-actions">
                <button className="ds-btn" onClick={() => setDeleting(null)}>取消</button>
                <button className="ds-btn ds-btn--danger" onClick={() => void remove()}>確認刪除</button>
              </div>
            </div>
          </div>
        )}
        {preview && (
          <div className="modal-inner-overlay modal-preview-overlay">
            <button className="ds-btn ds-btn--sm preview-back-btn" onClick={() => setPreview("")}><ArrowLeft size={14} /> 返回清單</button>
            <img src={preview} className="preview-full-img" alt="模板預覽" />
          </div>
        )}
      </div>
    </div>
  );
}
