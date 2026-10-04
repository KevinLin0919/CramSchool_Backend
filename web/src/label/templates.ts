import { apiFetch } from './http'
export const CANVAS_WIDTH = 800
export const CANVAS_HEIGHT = 600

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
// One side of the paper: its image, and the cells drawn on it in the 800×600
// canvas space of that image.
export type DraftPage = {
  pageIndex: number; imageId?: number
  width: number; height: number; preview: string; blob: Blob
  labels: Label[]
}
export type NameBoxDraft = { pageIndex: number; rect: Rect }
export type TemplateDraft = {
  id?: number; revision?: number
  name: string; unit: string; optionCount: number
  pages: DraftPage[]
  nameBox?: NameBoxDraft | null; nameBoxDirty: boolean
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

// Question numbers run across the whole paper, page after page: grading keys
// answers by number per paper. A new paper is numbered in reading order from
// the first page on; a saved one keeps its numbers and new cells continue
// after the highest number it has ever had.
export function numberPages<T extends Rect & { questionNo?: number }>(
  pages: { width: number; height: number; labels: T[] }[], saved: boolean, maxQuestionNo: number,
): T[][] {
  let next = saved ? Math.max(maxQuestionNo, ...pages.flatMap(p => p.labels.map(l => l.questionNo ?? 0))) : 0
  return pages.map(page => sortLabels(page.labels, page.width, page.height)
    .map(label => ({ ...label, questionNo: saved ? label.questionNo ?? ++next : ++next })))
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
  if (!data.pages.length) throw new Error('模板沒有母卷影像')
  const sorted = [...data.pages].sort((a, b) => a.page_index - b.page_index)
  const blobs = await Promise.all(sorted.map(p => masterBlob(id, undefined, p.page_index)))
  const pages: DraftPage[] = sorted.map((page, i) => ({
    pageIndex: page.page_index, imageId: page.image_id,
    width: page.image_width, height: page.image_height, blob: blobs[i]!, preview: URL.createObjectURL(blobs[i]!),
    labels: page.boxes.map(b => ({ ...toCanvas(b, page.image_width, page.image_height),
      questionNo: b.question_no, answer: b.answer, answerType: b.answer_type, answerTypeLocked: true, label: b.label })),
  }))
  const namePage = data.name_box ? pages.find(p => p.pageIndex === data.name_box!.page_index) : undefined
  return {
    id, revision: data.revision, name: data.exam_name, unit: data.unit ?? '', optionCount: data.option_count,
    pages,
    nameBox: data.name_box === undefined ? undefined : data.name_box && namePage
      ? { pageIndex: namePage.pageIndex, rect: toCanvas(data.name_box, namePage.width, namePage.height) } : null,
    nameBoxDirty: false,
    maxQuestionNo: Math.max(0, ...data.pages.flatMap(p => p.boxes.map(b => b.question_no))),
  }
}

const CIRCLED = '①②③④⑤⑥⑦⑧⑨⑩'
const MARKS = ['O', 'o', '○', '◯', '圈', 'X', 'x', '✕', '✖', '✗', '×', '叉']

// Three kinds, the ones the app grades today: 是非 (mark), 選擇 (choice) and
// 填空 (digit, numbers only for now). The detector finds cells but not their
// kind, so the kind comes from the answer the teacher types. A lone 1–4 reads
// as an option — on these papers "2" is almost always ② — and the teacher can
// override any cell or a run of them.
export function guessAnswerType(answer: string): AnswerType {
  const value = answer.trim()
  if (!value) return 'choice'
  if (MARKS.includes(value)) return 'mark'
  if (/^[A-E]$/i.test(value) || CIRCLED.includes(value)) return 'choice'
  if (/^[1-4]$/.test(value)) return 'choice'
  return 'digit'
}
export function updateAnswerType(label: Label) {
  if (!label.answerTypeLocked) label.answerType = guessAnswerType(label.answer)
}
export function normalizedAnswer(label: Label): string {
  const value = label.answer.trim()
  if (!value) return value
  if (label.answerType === 'mark' && !MARKS.includes(value)) throw new Error('是非題正解請輸入 ○ 或 ✕')
  if (label.answerType === 'digit' && !/^\d+$/.test(value)) throw new Error('填空題目前只支援整數答案')
  if (label.answerType !== 'choice') return value
  const number = /^[A-E]$/i.test(value) ? value.toUpperCase().charCodeAt(0) - 64
    : CIRCLED.includes(value) ? CIRCLED.indexOf(value) + 1
    : /^(?:[1-9]|10)$/.test(value) ? Number(value) : NaN
  if (!Number.isInteger(number)) throw new Error('選擇題正解請輸入 A–E、①–⑩ 或 1–10')
  return String(number)
}
export function answerError(label: Label): string {
  try { normalizedAnswer(label); return '' } catch (err) {
    return err instanceof Error ? err.message : '選擇題正解不合法'
  }
}

// The server keeps one option count per paper, which both grading and the
// report's option chart read. Papers mix three- and four-option questions, so
// rather than ask, take four or the highest option any answer uses, and never
// shrink what a loaded template already had.
function optionCountFor(draft: TemplateDraft, boxes: { answer: string; answer_type: AnswerType }[]): number {
  const highest = Math.max(0, ...boxes.filter(b => b.answer_type === 'choice' && b.answer).map(b => Number(b.answer)))
  return Math.min(10, Math.max(4, highest, draft.id ? draft.optionCount : 0))
}

export async function saveTemplate(draft: TemplateDraft): Promise<void> {
  if (!draft.name.trim()) throw new Error('請輸入考卷名稱')
  if (Array.from(draft.unit).length > 40) throw new Error('單元不可超過 40 字')
  if (!draft.pages.some(p => p.labels.some(l => l.answer.trim()))) throw new Error('至少一格有正解才能存')
  const numbered = numberPages(draft.pages, !!draft.id, draft.maxQuestionNo)
  const pageBoxes = draft.pages.map((page, i) => numbered[i]!.map(l => ({ ...toNormalized(l, page.width, page.height),
    question_no: l.questionNo, answer: normalizedAnswer(l), answer_type: l.answerType, label: l.label })))
  const payload: Record<string, unknown> = {
    exam_name: draft.name.trim(), unit: draft.unit || null, option_count: optionCountFor(draft, pageBoxes.flat()),
  }
  const namePage = draft.nameBox ? draft.pages.find(p => p.pageIndex === draft.nameBox!.pageIndex) : undefined
  if (draft.nameBox && namePage && (!draft.id || draft.nameBoxDirty)) {
    payload.name_box = { page_index: namePage.pageIndex, ...toNormalized(draft.nameBox.rect, namePage.width, namePage.height) }
  } else if (draft.nameBoxDirty) payload.name_box = null
  for (const page of draft.pages) {
    if (page.imageId) continue
    const form = new FormData()
    form.append('file', page.blob, `page-${page.pageIndex + 1}.jpg`)
    const res = await apiFetch('/api/v1/images', { method: 'POST', body: form })
    page.imageId = (await res.json()).id
  }
  payload.pages = draft.pages.map((page, i) => ({ page_index: page.pageIndex, image_id: page.imageId, boxes: pageBoxes[i] }))
  const res = await apiFetch(draft.id ? `/api/v1/templates/${draft.id}` : '/api/v1/templates', {
    method: draft.id ? 'PATCH' : 'POST',
    headers: draft.id ? { 'If-Match': `"${draft.revision}"` } : {},
    body: JSON.stringify(payload),
  })
  const saved: TemplateDetail = await res.json()
  draft.id = saved.id
  draft.revision = saved.revision
  draft.pages.forEach((page, i) => { page.labels = numbered[i]! })
  draft.maxQuestionNo = Math.max(draft.maxQuestionNo, ...numbered.flat().map(l => l.questionNo ?? 0))
  draft.nameBoxDirty = false
}
export async function renameTemplate(template: TemplateSummary, name: string) {
  const res = await apiFetch(`/api/v1/templates/${template.id}`, { method: 'PATCH',
    headers: { 'If-Match': `"${template.revision}"` }, body: JSON.stringify({ exam_name: name }) })
  const saved: TemplateDetail = await res.json()
  template.exam_name = saved.exam_name
  template.revision = saved.revision
}
export async function deleteTemplate(id: number) {
  await apiFetch(`/api/v1/templates/${id}`, { method: 'DELETE' })
}

// A PDF answer key, rendered page by page on the server into the same JPEG a
// photo becomes, so every later step treats the pages as photos.
export type SourcePage = { source: string; pageNo: number; width: number; height: number; preview: string; blob: Blob }
export async function pdfPages(file: File): Promise<SourcePage[]> {
  const form = new FormData()
  form.append('file', file, file.name)
  const res = await apiFetch('/api/v1/templates/pdf-pages', { method: 'POST', body: form })
  const data: { pages: { page_no: number; width: number; height: number; image_base64: string }[] } = await res.json()
  return data.pages.map(p => {
    const bytes = Uint8Array.from(atob(p.image_base64), c => c.charCodeAt(0))
    const blob = new Blob([bytes], { type: 'image/jpeg' })
    return { source: file.name, pageNo: p.page_no, width: p.width, height: p.height, blob, preview: URL.createObjectURL(blob) }
  })
}
