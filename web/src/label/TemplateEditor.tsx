import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUpDown, Check, Clock, Crosshair, Move, RotateCw, Save, ScanText, UserRound, X, ZoomIn, ZoomOut,
} from "lucide-react";
import { go } from "../App";
import { toBase64 } from "./imaging";
import {
  CANVAS_HEIGHT, CANVAS_WIDTH, answerError, computeFit, guessAnswerType, mergeDetections, readTemplate,
  saveTemplate, sortLabels, type AnswerType, type Rect, type TemplateDraft,
} from "./templates";
import { apiFetch } from "./http";
import { getDraft, newUid, setDraft, toTemplateLabel, toViewLabel, type ViewLabel } from "./draft";
import { askConfirm, showToast } from "./feedback";

const DEFAULT_CLASS = "答案區";
const TYPES = [
  { value: "choice", label: "選擇" }, { value: "mark", label: "是非" }, { value: "digit", label: "填空" },
] as const;
const PLACEHOLDER: Record<string, string> = { choice: "例：B 或 2", mark: "○ 或 ✕", digit: "數字" };

type Mode = "draw" | "pan" | "name";
type Gesture =
  | { kind: "draw"; x: number; y: number }
  | { kind: "pan"; x: number; y: number }
  | { kind: "move"; index: number; dx: number; dy: number };

// Printed answers come back as whatever Google read in the cell: keep the
// first line, drop spaces and the brackets or full stop around it.
const cleanAnswer = (text: string) =>
  (text.split("\n").map((t) => t.trim()).find(Boolean) ?? "")
    .replace(/\s+/g, "")
    .replace(/^[（(［[【]+|[)）］\]】。．.、,，]+$/g, "");

// The original editor, on the report's page. `templateId` opens a saved
// template; without it the editor works on the paper just uploaded.
export default function TemplateEditor({ templateId }: { templateId?: number }) {
  const [draft, setLocalDraft] = useState<TemplateDraft | null>(() => (templateId ? null : getDraft()));
  const [labels, setLabels] = useState<ViewLabel[]>(() => (templateId ? [] : (getDraft()?.labels ?? []).map(toViewLabel)));
  const [name, setName] = useState(() => (templateId ? "" : getDraft()?.name ?? ""));
  const [unit, setUnit] = useState(() => (templateId ? "" : getDraft()?.unit ?? ""));
  const [nameBox, setNameBox] = useState<Rect | null | undefined>(() => (templateId ? undefined : getDraft()?.nameBox));
  const [nameBoxDirty, setNameBoxDirty] = useState(false);
  const [loadError, setLoadError] = useState("");

  const [mode, setMode] = useState<Mode>("draw");
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [selected, setSelected] = useState(-1);
  const [drawing, setDrawing] = useState<Rect | null>(null);
  const [hover, setHover] = useState(-1);
  const [ctrl, setCtrl] = useState(false);
  const [checked, setChecked] = useState<number[]>([]);

  const [predicting, setPredicting] = useState(false);
  const [predictionError, setPredictionError] = useState("");
  const [predictionsLoaded, setPredictionsLoaded] = useState(() => !templateId && !!getDraft()?.labels.length);
  const [ocr, setOcr] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  const canvas = useRef<HTMLCanvasElement>(null);
  const image = useRef<HTMLImageElement | null>(null);
  const [imageReady, setImageReady] = useState(0);
  const gesture = useRef<Gesture | null>(null);
  const inputs = useRef<(HTMLInputElement | null)[]>([]);
  const lastChecked = useRef(-1);
  const alive = useRef(true);

  const readOnly = (draft?.pageCount ?? 0) > 1;
  const locked = readOnly || saving || predicting;
  const labelError = (l: ViewLabel) => answerError(toTemplateLabel(l));
  const invalidAnswers = labels.some((l) => labelError(l));
  const hasAnswers = labels.some((l) => l.expectedAnswer.trim());
  const invalidMetadata = !name.trim() || Array.from(unit).length > 40;

  const questionNumbers = useMemo(() => {
    const numbers = new Map<number, number>();
    if (!draft) return numbers;
    let next = Math.max(draft.maxQuestionNo, ...labels.map((l) => l.questionNo ?? 0));
    sortLabels(labels, draft.width, draft.height).forEach((l, i) => numbers.set(l.uid, draft.id ? l.questionNo ?? ++next : i + 1));
    return numbers;
  }, [labels, draft]);

  useEffect(() => () => { alive.current = false; }, []);

  // Leaving mid-edit (to the report and back) keeps the work: what is on
  // screen goes back into the draft the upload page will reopen.
  const latest = useRef({ labels, name, unit, nameBox, nameBoxDirty });
  latest.current = { labels, name, unit, nameBox, nameBoxDirty };
  useEffect(() => () => {
    const d = getDraft();
    if (!d || d.id) return;
    const { labels: ls, ...rest } = latest.current;
    Object.assign(d, rest, { labels: ls.map(toTemplateLabel) });
  }, []);

  // A saved template is loaded here; a fresh upload arrives through the draft.
  useEffect(() => {
    if (!templateId) {
      if (!getDraft()) go("/templates");
      return;
    }
    readTemplate(templateId).then((value) => {
      if (!alive.current) { URL.revokeObjectURL(value.preview); return; }
      setDraft(value);
      setLocalDraft(value);
      setLabels(value.labels.map(toViewLabel));
      setName(value.name);
      setUnit(value.unit);
      setNameBox(value.nameBox);
      setPredictionsLoaded(true);
    }).catch((e) => setLoadError(e instanceof Error ? e.message : "載入模板失敗"));
  }, [templateId]);

  useEffect(() => {
    if (!draft) return;
    const img = new Image();
    img.onload = () => { image.current = img; setImageReady((n) => n + 1); };
    img.src = draft.preview;
  }, [draft]);

  // Paint whenever anything on the canvas changes.
  useEffect(() => {
    const el = canvas.current;
    const img = image.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx || !img) return;
    el.width = CANVAS_WIDTH;
    el.height = CANVAS_HEIGHT;
    ctx.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    const fit = computeFit(img.width, img.height);
    const css = getComputedStyle(el);
    const colour = (v: string) => css.getPropertyValue(v).trim();
    ctx.save();
    ctx.setTransform(zoom, 0, 0, zoom, pan.x, pan.y);
    ctx.drawImage(img, fit.offsetX, fit.offsetY, img.width * fit.scale, img.height * fit.scale);
    labels.forEach((l, i) => {
      ctx.strokeStyle = colour(i === selected ? "--danger" : "--accent");
      ctx.lineWidth = i === selected ? 3 : 2;
      ctx.strokeRect(l.x, l.y, l.width, l.height);
    });
    ctx.strokeStyle = colour("--name-box");
    ctx.lineWidth = 2;
    if (nameBox) {
      ctx.strokeRect(nameBox.x, nameBox.y, nameBox.width, nameBox.height);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = '13px "Noto Sans TC", sans-serif';
      ctx.fillText("姓名", nameBox.x, nameBox.y - 4);
    }
    if (drawing) {
      if (mode !== "name") ctx.strokeStyle = colour("--danger");
      ctx.strokeRect(drawing.x, drawing.y, drawing.width, drawing.height);
    }
    ctx.restore();
  }, [labels, selected, zoom, pan, drawing, nameBox, mode, imageReady]);

  const detect = useCallback(async (existing: ViewLabel[]) => {
    const value = getDraft();
    if (!value || value.pageCount > 1) return;
    setPredicting(true);
    setPredictionError("");
    try {
      const { scale, offsetX, offsetY } = computeFit(value.width, value.height);
      const res = await apiFetch("/api/v1/templates/detect", {
        method: "POST", body: JSON.stringify({ image_base64: await toBase64(value.blob) }),
      });
      const data: { detections: { bbox: number[]; confidence?: number }[] } = await res.json();
      const found: ViewLabel[] = data.detections.map((d) => {
        const [x1 = 0, y1 = 0, x2 = 0, y2 = 0] = d.bbox;
        return {
          uid: newUid(), class: DEFAULT_CLASS, x: Math.max(0, x1 * scale + offsetX), y: Math.max(0, y1 * scale + offsetY),
          width: Math.abs(x2 - x1) * scale, height: Math.abs(y2 - y1) * scale,
          confidence: d.confidence, expectedAnswer: "", answerType: "choice",
        };
      });
      if (!alive.current) return;
      const merged = mergeDetections(existing.map(toTemplateLabel), found.map(toTemplateLabel)).map(toViewLabel);
      // A first detection is put in reading order, as the original did.
      setLabels(existing.length ? merged : sortLabels(merged, value.width, value.height));
      setPredictionsLoaded(true);
    } catch (e) {
      if (alive.current) setPredictionError(e instanceof Error ? e.message : "自動偵測失敗，請確認連線後重試");
    } finally {
      if (alive.current) setPredicting(false);
    }
  }, []);

  // A fresh upload is detected once on arrival.
  const detectedOnce = useRef(false);
  useEffect(() => {
    if (templateId || detectedOnce.current || !draft || draft.id || labels.length) return;
    detectedOnce.current = true;
    void detect([]);
  }, [templateId, draft, labels.length, detect]);

  // Keys: Ctrl shows the pan cursor; Delete removes the selected cell when
  // focus is not in a field.
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "Control") setCtrl(true);
      if ((e.key === "Backspace" || e.key === "Delete") && selected !== -1 && !locked) {
        const el = document.activeElement;
        if (el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement || (el as HTMLElement)?.isContentEditable) return;
        e.preventDefault();
        removeLabel(selected);
      }
    };
    const up = (e: KeyboardEvent) => { if (e.key === "Control") setCtrl(false); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  });

  const coords = (e: React.MouseEvent | React.WheelEvent) => {
    const el = canvas.current!;
    const r = el.getBoundingClientRect();
    const sx = r.width > 0 ? el.width / r.width : 1, sy = r.height > 0 ? el.height / r.height : 1;
    return { cx: (e.clientX - r.left) * sx, cy: (e.clientY - r.top) * sy };
  };
  const toImage = (cx: number, cy: number) => ({ x: (cx - pan.x) / zoom, y: (cy - pan.y) / zoom });
  const hitTest = (x: number, y: number) => {
    for (let i = labels.length - 1; i >= 0; i--) {
      const l = labels[i]!;
      if (x >= l.x && x <= l.x + l.width && y >= l.y && y <= l.y + l.height) return i;
    }
    return -1;
  };

  const focusInput = (i: number) => requestAnimationFrame(() => inputs.current[i]?.focus());

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    const { cx, cy } = coords(e);
    if (locked) { gesture.current = { kind: "pan", x: e.clientX, y: e.clientY }; return; }
    const panMode = mode === "pan" || e.ctrlKey;
    const { x, y } = toImage(cx, cy);
    const hit = mode !== "name" || panMode ? hitTest(x, y) : -1;
    if (panMode) {
      if (hit !== -1) {
        setSelected(hit);
        gesture.current = { kind: "move", index: hit, dx: x - labels[hit]!.x, dy: y - labels[hit]!.y };
        focusInput(hit);
      } else gesture.current = { kind: "pan", x: e.clientX, y: e.clientY };
      return;
    }
    if (hit !== -1) { setSelected(hit); focusInput(hit); return; }
    setSelected(-1);
    gesture.current = { kind: "draw", x, y };
    setDrawing({ x, y, width: 0, height: 0 });
  };

  const onMouseMove = (e: React.MouseEvent) => {
    const g = gesture.current;
    const { cx, cy } = coords(e);
    const { x, y } = toImage(cx, cy);
    if (g?.kind === "pan") {
      const dx = e.clientX - g.x, dy = e.clientY - g.y;
      g.x = e.clientX; g.y = e.clientY;
      setPan((p) => ({ x: p.x + dx, y: p.y + dy }));
      return;
    }
    if (locked) return;
    if (g?.kind === "move") {
      setLabels((ls) => ls.map((l, i) => (i === g.index ? { ...l, x: x - g.dx, y: y - g.dy } : l)));
      return;
    }
    if (!g) { const h = hitTest(x, y); if (h !== hover) setHover(h); return; }
    setDrawing({ x: Math.min(g.x, x), y: Math.min(g.y, y), width: Math.abs(x - g.x), height: Math.abs(y - g.y) });
  };

  const onMouseUp = () => {
    const g = gesture.current;
    gesture.current = null;
    if (g?.kind !== "draw") return;
    const rect = drawing;
    setDrawing(null);
    if (locked || !rect || rect.width <= 10 || rect.height <= 10) return;
    if (mode === "name") { setNameBox(rect); setNameBoxDirty(true); return; }
    const next = [...labels, { ...rect, uid: newUid(), class: DEFAULT_CLASS, expectedAnswer: "", answerType: "choice" as AnswerType }];
    setLabels(next);
    setSelected(next.length - 1);
    focusInput(next.length - 1);
  };

  const zoomAt = (cx: number, cy: number, target: number) => {
    const next = Math.min(3, Math.max(0.2, target));
    if (next === zoom) return;
    setPan((p) => ({ x: cx - ((cx - p.x) / zoom) * next, y: cy - ((cy - p.y) / zoom) * next }));
    setZoom(next);
  };
  // React's wheel listener is passive, so the page would scroll too; attach one that is not.
  const zoomRef = useRef(zoomAt);
  zoomRef.current = zoomAt;
  const zoomValue = useRef(zoom);
  zoomValue.current = zoom;
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomRef.current((e.clientX - r.left) * (el.width / r.width), (e.clientY - r.top) * (el.height / r.height), zoomValue.current + (e.deltaY < 0 ? 0.1 : -0.1));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [draft]);

  const cursor = gesture.current?.kind === "pan" || gesture.current?.kind === "move" ? "grabbing"
    : mode === "pan" || ctrl ? "grab" : "crosshair";

  const update = (i: number, patch: Partial<ViewLabel>) => setLabels((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  const setAnswer = (i: number, value: string) => {
    const l = labels[i]!;
    update(i, { expectedAnswer: value, ...(l.answerTypeLocked ? {} : { answerType: guessAnswerType(value) }) });
  };
  const setType = (i: number, type: AnswerType) => update(i, { answerType: type, answerTypeLocked: true });

  function removeLabel(i: number) {
    if (locked) return;
    const gone = labels[i];
    setLabels((ls) => ls.filter((_, j) => j !== i));
    setChecked((c) => c.filter((u) => u !== gone?.uid));
    setSelected((s) => (s === i ? -1 : s > i ? s - 1 : s));
  }

  const onInputKey = (i: number, e: React.KeyboardEvent<HTMLInputElement>) => {
    if (locked) return;
    if (e.key === "Enter") { e.preventDefault(); if (i + 1 < labels.length) focusInput(i + 1); return; }
    if ((e.key === "Backspace" || e.key === "Delete") && labels[i]!.expectedAnswer === "") { e.preventDefault(); removeLabel(i); }
  };

  // Ticked runs of cells take one type at once; Shift ticks a range.
  const allChecked = labels.length > 0 && labels.every((l) => checked.includes(l.uid));
  const toggleCheck = (i: number, shift: boolean) => {
    const l = labels[i]!;
    const on = !checked.includes(l.uid);
    const range = (shift && lastChecked.current >= 0
      ? labels.slice(Math.min(lastChecked.current, i), Math.max(lastChecked.current, i) + 1) : [l]).map((r) => r.uid);
    setChecked((c) => (on ? [...c, ...range.filter((r) => !c.includes(r))] : c.filter((r) => !range.includes(r))));
    lastChecked.current = i;
  };
  const applyBatchType = (type: AnswerType) => {
    const n = checked.length;
    setLabels((ls) => ls.map((l) => (checked.includes(l.uid) ? { ...l, answerType: type, answerTypeLocked: true } : l)));
    setChecked([]);
    showToast(`已將 ${n} 格設為${TYPES.find((t) => t.value === type)?.label}題`, "success");
  };

  const retryPrediction = async () => {
    if (locked) return;
    if (labels.length && !await askConfirm({ title: "重新偵測", message: "偵測會校正重疊的答案框並補上新框；既有題號與正解會保留，確定繼續嗎？", confirmText: "重新偵測" })) return;
    setSelected(-1);
    await detect(labels);
  };

  const autoSort = () => {
    if (locked || !draft || !labels.length) return;
    setLabels(sortLabels(labels, draft.width, draft.height));
    showToast(draft.height > draft.width
      ? "已偵測為直式考卷，排序完成（左半部優先，由上到下、由左到右）"
      : "已偵測為橫式考卷，排序完成（由上到下、由右到左）", "success");
  };

  // Printed answers on the master, read by Google Vision through the API and
  // written into the empty 正解 fields. Cells already filled are left alone.
  const detectAnswers = async () => {
    if (!draft || !labels.length) { showToast("請先在答案卷建立標註框", "error"); return; }
    setOcr(true);
    try {
      const { scale, offsetX, offsetY } = computeFit(draft.width, draft.height);
      const boxes = labels.map((l) => {
        const x1 = (l.x - offsetX) / scale, y1 = (l.y - offsetY) / scale;
        return [x1, y1, x1 + l.width / scale, y1 + l.height / scale];
      });
      const res = await apiFetch("/api/v1/templates/read-answers", {
        method: "POST", body: JSON.stringify({ image_base64: await toBase64(draft.blob), boxes }),
      });
      const { results } = (await res.json()) as { results: { text: string }[] };
      if (!alive.current) return;
      let filled = 0;
      setLabels((ls) => ls.map((l, i) => {
        const text = cleanAnswer(results[i]?.text ?? "");
        if (!text || l.expectedAnswer.trim()) return l;
        filled++;
        return { ...l, expectedAnswer: text, ...(l.answerTypeLocked ? {} : { answerType: guessAnswerType(text) }) };
      }));
      showToast(filled ? `已填入 ${filled} 格正解，請再核對一次` : "沒有讀到新的正解", filled ? "success" : "info");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "答案偵測失敗，請稍後再試", "error");
    } finally {
      if (alive.current) setOcr(false);
    }
  };

  const clearLabels = async () => {
    if (locked || !labels.length) return;
    if (!await askConfirm({ title: "清除標註", message: `確定要清除「${name}」的全部 ${labels.length} 個標註嗎？`, confirmText: "清除", danger: true })) return;
    setLabels([]);
    setChecked([]);
    setSelected(-1);
  };

  const reload = async () => {
    if (!draft?.id || locked) return;
    if (!await askConfirm({ title: "重新載入模板", message: "重新載入會捨棄尚未儲存的變更，確定繼續嗎？", confirmText: "重新載入", danger: true })) return;
    location.reload();
  };

  const save = async () => {
    if (!draft || locked || invalidAnswers || invalidMetadata || !hasAnswers) return;
    setSaving(true);
    setSaveError("");
    try {
      Object.assign(draft, { name, unit, nameBox, nameBoxDirty, labels: labels.map(toTemplateLabel) });
      await saveTemplate(draft);
      if (!alive.current) return;
      showToast("模板已儲存", "success");
      setDraft(null);
      go("/templates/list");
    } catch (e) {
      if (alive.current) setSaveError(e instanceof Error ? e.message : "儲存失敗，請稍後再試");
    } finally {
      if (alive.current) setSaving(false);
    }
  };

  if (loadError) {
    return (
      <div className="tpl"><div className="ds-card no-images">
        <p>{loadError}</p>
        <button onClick={() => go("/templates")} className="ds-btn ds-btn--primary">回到建立模板</button>
      </div></div>
    );
  }

  return (
    <div className="tpl">
      <div className="label-container">
        <div className="editor-head">
          <button type="button" className="crumb-link" onClick={() => go("/templates")}>建立模板</button>
          <span className="crumb-sep">/</span>
          <span>{draft?.id ? "編輯模板" : "新模板"}</span>
        </div>
        <div className="labeling-workspace labeling-workspace--embedded">
          <section className="ds-card canvas-card">
            <div className="canvas-toolbar">
              <div className="ds-segmented ds-segmented--sm">
                <button type="button" className={`ds-segmented__btn ${mode === "draw" ? "is-active" : ""}`} disabled={locked} onClick={() => setMode("draw")}>
                  <Crosshair size={14} /> 標註
                </button>
                <button type="button" className={`ds-segmented__btn ${mode === "pan" ? "is-active" : ""}`} onClick={() => setMode("pan")}>
                  <Move size={14} /> 拖移
                </button>
              </div>
              <button className={`ds-btn ds-btn--sm ${mode === "name" ? "ds-btn--primary" : ""}`} disabled={locked} onClick={() => setMode("name")}>
                <UserRound size={14} /> 框姓名欄
              </button>
              <span className="toolbar-hint">拖移可按住 Ctrl</span>
              <span className="spacer"></span>
              <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" onClick={() => zoomAt(CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2, zoom - 0.1)} title="縮小"><ZoomOut size={14} /></button>
              <span className="zoom-value">{Math.round(zoom * 100)}%</span>
              <button className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" onClick={() => zoomAt(CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2, zoom + 0.1)} title="放大"><ZoomIn size={14} /></button>
              <button className="ds-btn ds-btn--ghost ds-btn--sm" onClick={() => { setPan({ x: 0, y: 0 }); setZoom(1); }}>重置</button>
            </div>

            <div className="canvas-area">
              <canvas ref={canvas} tabIndex={0} style={{ cursor, outline: "none" }}
                onMouseDown={onMouseDown} onMouseMove={onMouseMove} onMouseUp={onMouseUp} onMouseLeave={onMouseUp} />
            </div>

            <div className="canvas-footer">
              {predicting ? (
                <span className="ds-badge ds-badge--pending"><Clock size={11} /> 偵測中…</span>
              ) : predictionError ? (
                <>
                  <span className="ds-badge ds-badge--wrong"><X size={11} /> {predictionError}</span>
                  <button onClick={() => void retryPrediction()} disabled={locked} className="ds-btn ds-btn--ghost ds-btn--sm">重試</button>
                </>
              ) : predictionsLoaded && !draft?.id && !labels.length ? (
                <span className="ds-badge ds-badge--pending">沒有偵測到答案格，請在圖上手動框選</span>
              ) : predictionsLoaded ? (
                <span className="ds-badge ds-badge--correct"><Check size={11} /> {draft?.id ? "已載入模板" : "已套用偵測結果"}</span>
              ) : (
                <span className="ds-badge">{draft ? "等待偵測" : "載入中…"}</span>
              )}
            </div>
          </section>

          <aside className="side-panel">
            <div className="ds-card panel-card">
              <p className="ds-eyebrow panel-label">考卷資訊</p>
              <div className="template-fields">
                <label className="hint-text">考卷名稱<input value={name} onChange={(e) => setName(e.target.value)} className="ds-input ds-input--sm" maxLength={255} disabled={locked} /></label>
                <label className="hint-text">單元<input value={unit} onChange={(e) => setUnit(e.target.value)} className="ds-input ds-input--sm" maxLength={40} placeholder="選填，最多 40 字" disabled={locked} /></label>
              </div>
              {readOnly && <p className="ds-banner ds-banner--warning">這份考卷有多頁，網頁目前只能檢視第一頁</p>}
              {invalidMetadata && draft && <p className="hint-text field-error">請填入考卷名稱，單元最多 40 字。</p>}
              <p className="ds-eyebrow panel-label">工具</p>
              <div className="batch-grid">
                <button onClick={() => void retryPrediction()} disabled={locked} className="ds-btn ds-btn--sm"><RotateCw size={14} /> 重新偵測</button>
                <button onClick={autoSort} disabled={locked || !labels.length} className="ds-btn ds-btn--sm"><ArrowUpDown size={14} /> 自動排序</button>
                <button onClick={() => void detectAnswers()} disabled={locked || ocr || !labels.length} className="ds-btn ds-btn--sm">
                  <ScanText size={14} /> {ocr ? "辨識中…" : "答案偵測"}
                </button>
              </div>
              {nameBox && (
                <div className="class-row name-box-row">
                  <span className="ds-badge">已框選姓名欄</span>
                  <button className="ds-btn ds-btn--danger ds-btn--sm" disabled={locked} onClick={() => { setNameBox(null); setNameBoxDirty(true); }}>刪除姓名框</button>
                </div>
              )}
            </div>

            <div className="ds-card panel-card">
              <p className="ds-eyebrow panel-label">目前標註（{labels.length}）</p>
              {labels.length > 0 && (
                <>
                  <div className="batch-bar">
                    <label className="batch-all hint-text">
                      <input type="checkbox" checked={allChecked} disabled={locked}
                        ref={(el) => { if (el) el.indeterminate = checked.length > 0 && !allChecked; }}
                        onChange={() => setChecked(allChecked ? [] : labels.map((l) => l.uid))} />
                      {checked.length ? `已選 ${checked.length} 格` : "全選"}
                    </label>
                    <div className="type-toggle" role="group" aria-label="把勾選的格子設為">
                      {TYPES.map((t) => (
                        <button key={t.value} type="button" className="ds-btn ds-btn--sm" disabled={locked || !checked.length} onClick={() => applyBatchType(t.value)}>設為{t.label}</button>
                      ))}
                    </div>
                  </div>
                  <p className="hint-text batch-hint">勾選要設定的格子，按住 Shift 可一次勾選一整段。</p>
                  <div className="label-scroll">
                    {labels.map((l, i) => {
                      const err = labelError(l);
                      const no = questionNumbers.get(l.uid);
                      return (
                        <div key={l.uid} className={`label-item ${i === selected ? "selected" : ""} ${err ? "invalid" : ""}`} onClick={() => focusInput(i)}>
                          <input type="checkbox" className="label-check" checked={checked.includes(l.uid)} disabled={locked} aria-label={`勾選第 ${no} 題`}
                            onClick={(e) => { e.stopPropagation(); toggleCheck(i, e.shiftKey); }} onChange={() => {}} />
                          <span className="label-index">#{no}</span>
                          <span className="label-name">{l.class}</span>
                          <span className="label-expected">
                            <span className="input-prefix">正解</span>
                            <input type="text" value={l.expectedAnswer} disabled={locked} aria-invalid={!!err} title={err}
                              placeholder={PLACEHOLDER[l.answerType] ?? ""} className="ds-input ds-input--sm ds-input--mono expected-value"
                              ref={(el) => { inputs.current[i] = el; }}
                              onChange={(e) => setAnswer(i, e.target.value)} onFocus={() => setSelected(i)}
                              onKeyDown={(e) => onInputKey(i, e)} onClick={(e) => e.stopPropagation()} />
                          </span>
                          <button onClick={(e) => { e.stopPropagation(); removeLabel(i); }} disabled={locked} className="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" title="刪除標註"><X size={14} /></button>
                          <div className="label-type type-toggle" role="radiogroup" aria-label={`第 ${no} 題題型`} onClick={(e) => e.stopPropagation()}>
                            {TYPES.map((t) => (
                              <button key={t.value} type="button" role="radio" aria-checked={l.answerType === t.value}
                                className={`ds-btn ds-btn--sm ${l.answerType === t.value ? "on" : ""}`} disabled={locked} onClick={() => setType(i, t.value)}>{t.label}</button>
                            ))}
                          </div>
                          {err && <p className="hint-text field-error" role="alert">{err}</p>}
                        </div>
                      );
                    })}
                  </div>
                </>
              )}
              {!labels.length && <p className="no-labels">尚無標註，請在圖上拖曳畫框。</p>}
            </div>

            <div className="ds-card ds-card--sunken panel-card">
              <div className="panel-actions">
                <button onClick={() => void clearLabels()} disabled={locked} className="ds-btn ds-btn--danger ds-btn--sm">清除標註</button>
              </div>
              {saveError && (
                <p className="ds-banner ds-banner--danger" role="alert">{saveError}
                  {draft?.id && <button className="ds-btn ds-btn--sm" onClick={() => void reload()}>重新載入</button>}
                </p>
              )}
              <button onClick={() => void save()} disabled={locked || invalidAnswers || invalidMetadata || !hasAnswers} className="ds-btn ds-btn--primary results-btn">
                <Save size={16} /> {saving ? "儲存中…" : "儲存模板"}
              </button>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
