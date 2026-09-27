import { apiFetch } from './api'
import { CANVAS_WIDTH, CANVAS_HEIGHT } from './constants'

export type AnswerType = 'choice' | 'mark' | 'digit' | 'chinese' | 'text'
export type Rect = { x: number; y: number; width: number; height: number }
type NormalizedRect = { x: number; y: number; w: number; h: number }
export type Label = Rect & {
  questionNo?: number
  answer: string
  answerType: AnswerType
  answerTypeLocked?: boolean
  label: string
  confidence?: number
}
export type TemplateSummary = {
  id: number; exam_name: string; annotation_count: number; created_at: string
  page_count: number; revision: number
}
type Page = {
  page_index: number; image_id: number; image_width: number; image_height: number
  boxes: (NormalizedRect & { question_no: number; answer: string; answer_type: AnswerType; label: string })[]
}
type TemplateDetail = TemplateSummary & {
  unit: string | null; option_count: number
  name_box?: (NormalizedRect & { page_index: number }) | null
  pages: Page[]
}
export type TemplateDraft = {
  id?: number; revision?: number; imageId?: number; pageIndex: number; pageCount: number
  name: string; unit: string; optionCount: number
  // Editor-only: how a typed "2" is read. Not stored on the server, where
  // each box's answer_type already carries the decision.
  singleDigitAs: SingleDigitAs
  width: number; height: number; preview: string; blob: Blob
  labels: Label[]; nameBox?: Rect | null; nameBoxDirty: boolean
  // Retain the highest loaded number even when its box is deleted.
  maxQuestionNo: number
}

export function computeFit(width: number, height: number) {
  const scale = Math.min(CANVAS_WIDTH / width, CANVAS_HEIGHT / height)
  return { scale, offsetX: (CANVAS_WIDTH - width * scale) / 2, offsetY: (CANVAS_HEIGHT - height * scale) / 2 }
}
export function toCanvas(box: NormalizedRect, width: number, height: number): Rect {
  const { scale, offsetX, offsetY } = computeFit(width, height)
  return { x: box.x * width * scale + offsetX, y: box.y * height * scale + offsetY,
    width: box.w * width * scale, height: box.h * height * scale }
}
export function toNormalized(box: Rect, width: number, height: number): NormalizedRect {
  const { scale, offsetX, offsetY } = computeFit(width, height)
  const clamp = (n: number) => Math.max(0, Math.min(1, n))
  const x = clamp((box.x - offsetX) / (width * scale))
  const y = clamp((box.y - offsetY) / (height * scale))
  const right = clamp((box.x + box.width - offsetX) / (width * scale))
  const bottom = clamp((box.y + box.height - offsetY) / (height * scale))
  if (right <= x || bottom <= y) throw new Error('標註框必須位於圖片內，請移動或刪除留白處的框')
  return { x, y, w: right - x, h: bottom - y }
}

// The original canvas order: portrait columns left first, landscape rows right first.
export function sortLabels<T extends Rect>(labels: T[], width: number, height: number): T[] {
  const centers = labels.map(l => l.x + l.width / 2).sort((a, b) => a - b)
  const midLine = centers[Math.floor(centers.length / 2)] ?? 0
  return [...labels].sort((a, b) => {
    if (height > width) {
      const leftA = a.x + a.width / 2 < midLine
      const leftB = b.x + b.width / 2 < midLine
      if (leftA !== leftB) return leftA ? -1 : 1
    }
    if (Math.abs(a.y - b.y) > 10) return a.y - b.y
    return height > width ? a.x - b.x : b.x - a.x
  })
}
// Match overlapping detections once, keeping the existing grade keys and answers.
export function mergeDetections(existing: Label[], detected: Label[]): Label[] {
  const remaining = new Set(detected)
  const merged = existing.map(label => {
    let best: Label | undefined
    let bestOverlap = 0.3
    for (const candidate of remaining) {
      const intersection = Math.max(0, Math.min(label.x + label.width, candidate.x + candidate.width) - Math.max(label.x, candidate.x))
        * Math.max(0, Math.min(label.y + label.height, candidate.y + candidate.height) - Math.max(label.y, candidate.y))
      const overlap = intersection / (label.width * label.height + candidate.width * candidate.height - intersection)
      if (overlap > bestOverlap) { best = candidate; bestOverlap = overlap }
    }
    if (!best) return label
    remaining.delete(best)
    return { ...label, x: best.x, y: best.y, width: best.width, height: best.height, confidence: best.confidence }
  })
  return [...merged, ...remaining]
}

export function numberedLabels(draft: TemplateDraft): Label[] {
  const ordered = sortLabels(draft.labels, draft.width, draft.height)
  let next = Math.max(draft.maxQuestionNo, ...draft.labels.map(l => l.questionNo ?? 0))
  return ordered.map((label, i) => ({ ...label, questionNo: draft.id ? label.questionNo ?? ++next : i + 1 }))
}

export async function listTemplates(search = ''): Promise<TemplateSummary[]> {
  const res = await apiFetch(`/api/v1/templates?search=${encodeURIComponent(search)}`)
  return (await res.json()).templates
}
export async function masterBlob(id: number, width?: number, page = 0): Promise<Blob> {
  const params = new URLSearchParams({ page: String(page) })
  if (width) params.set('w', String(width))
  const res = await apiFetch(`/api/v1/templates/${id}/master?${params}`)
  return res.blob()
}
export async function readTemplate(id: number): Promise<TemplateDraft> {
  const res = await apiFetch(`/api/v1/templates/${id}`)
  const data: TemplateDetail = await res.json()
  const page = data.pages[0]
  if (!page) throw new Error('模板沒有母卷影像')
  const blob = await masterBlob(id, undefined, page.page_index)
  return {
    id, revision: data.revision, imageId: page.image_id, pageIndex: page.page_index,
    pageCount: data.page_count, name: data.exam_name, unit: data.unit ?? '', optionCount: data.option_count, singleDigitAs: 'choice',
    width: page.image_width, height: page.image_height, blob, preview: URL.createObjectURL(blob),
    labels: page.boxes.map(b => ({ ...toCanvas(b, page.image_width, page.image_height),
      questionNo: b.question_no, answer: b.answer, answerType: b.answer_type, answerTypeLocked: true, label: b.label })),
    nameBox: data.name_box === undefined ? undefined : data.name_box && data.name_box.page_index === page.page_index
      ? toCanvas(data.name_box, page.image_width, page.image_height) : null,
    nameBoxDirty: false,
    maxQuestionNo: Math.max(0, ...page.boxes.map(b => b.question_no)),
  }
}

// How a lone number such as "2" reads on this paper: an option (①–④) or a
// numeric answer. The detector only finds cells, so the type comes from the
// answer the teacher types, and this is the one thing an answer cannot tell.
export type SingleDigitAs = 'choice' | 'digit'

const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩'

// Follows app/coords.py (digits, circle/cross marks, CJK ideographs, else
// text), plus the two shapes only a choice question has: a letter A–E and a
// circled number.
export function guessAnswerType(answer: string, optionCount = 4, singleDigitAs: SingleDigitAs = 'choice'): AnswerType {
  const value = answer.trim()
  if (!value) return 'text'
  if (/^[A-E]$/i.test(value) || CIRCLED.includes(value)) return 'choice'
  if (/^(?:[1-9]|10)$/.test(value) && Number(value) <= optionCount && singleDigitAs === 'choice') return 'choice'
  if (/^\p{Decimal_Number}+$/u.test(value)) return 'digit'
  if (['O', 'o', '○', '◯', '圈', 'X', 'x', '✕', '✗', '×', '叉'].includes(value)) return 'mark'
  if (/^[一-鿿]+$/u.test(value)) return 'chinese'
  return 'text'
}
export function updateAnswerType(label: Label) {
  if (!label.answerTypeLocked) label.answerType = guessAnswerType(label.answer)
}
export function normalizedAnswer(label: Label, optionCount: number): string {
  const value = label.answer.trim()
  if (label.answerType !== 'choice' || !value) return value
  const number = /^[A-E]$/i.test(value) ? value.toUpperCase().charCodeAt(0) - 64
    : CIRCLED.includes(value) ? CIRCLED.indexOf(value) + 1
    : /^(?:[1-9]|10)$/.test(value) ? Number(value) : NaN
  if (!Number.isInteger(number) || number > optionCount) throw new Error(`選擇題正解請輸入 A–E、①–⑩ 或 1–${optionCount}，且不可超過選項數`)
  return String(number)
}
export function answerError(label: Label, optionCount: number): string {
  try { normalizedAnswer(label, optionCount); return '' } catch (err) {
    return err instanceof Error ? err.message : '選擇題正解不合法'
  }
}

export async function saveTemplate(draft: TemplateDraft): Promise<void> {
  if (draft.pageCount > 1) throw new Error('多頁模板請在 App 編輯')
  if (!draft.name.trim()) throw new Error('請輸入考卷名稱')
  if (Array.from(draft.unit).length > 40) throw new Error('單元不可超過 40 字')
  if (!Number.isInteger(draft.optionCount) || draft.optionCount < 2 || draft.optionCount > 10) throw new Error('選項數須為 2–10')
  if (!draft.labels.some(l => l.answer.trim())) throw new Error('至少一格有正解才能存')
  const labels = numberedLabels(draft)
  const boxes = labels.map(l => ({ ...toNormalized(l, draft.width, draft.height),
    question_no: l.questionNo, answer: normalizedAnswer(l, draft.optionCount), answer_type: l.answerType, label: l.label }))
  const payload: Record<string, unknown> = { exam_name: draft.name.trim(), unit: draft.unit || null, option_count: draft.optionCount }
  if (draft.nameBox && (!draft.id || draft.nameBoxDirty)) payload.name_box = { page_index: draft.pageIndex, ...toNormalized(draft.nameBox, draft.width, draft.height) }
  else if (draft.nameBoxDirty) payload.name_box = null
  if (!draft.imageId) {
    const form = new FormData()
    form.append('file', draft.blob, 'master.jpg')
    const res = await apiFetch('/api/v1/images', { method: 'POST', body: form })
    draft.imageId = (await res.json()).id
  }
  payload.pages = [{ page_index: draft.pageIndex, image_id: draft.imageId, boxes }]
  const res = await apiFetch(draft.id ? `/api/v1/templates/${draft.id}` : '/api/v1/templates', {
    method: draft.id ? 'PATCH' : 'POST',
    headers: draft.id ? { 'If-Match': `"${draft.revision}"` } : {},
    body: JSON.stringify(payload),
  })
  const saved: TemplateDetail = await res.json()
  draft.id = saved.id
  draft.revision = saved.revision
  draft.labels = labels
  draft.maxQuestionNo = Math.max(draft.maxQuestionNo, ...labels.map(l => l.questionNo ?? 0))
  draft.nameBoxDirty = false
}
export async function renameTemplate(template: TemplateSummary, name: string) {
  if (template.page_count > 1) throw new Error('多頁模板請在 App 編輯')
  const res = await apiFetch(`/api/v1/templates/${template.id}`, { method: 'PATCH',
    headers: { 'If-Match': `"${template.revision}"` }, body: JSON.stringify({ exam_name: name }) })
  const saved: TemplateDetail = await res.json()
  template.exam_name = saved.exam_name
  template.revision = saved.revision
}
export async function deleteTemplate(id: number) {
  await apiFetch(`/api/v1/templates/${id}`, { method: 'DELETE' })
}
