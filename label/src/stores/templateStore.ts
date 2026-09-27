import { ref } from 'vue'
import { guessAnswerType, type TemplateDraft, type Label, type AnswerType, type Rect } from '../templates'
import { clearAllData, initializeFromUpload } from './resultsStore'

export const draft = ref<TemplateDraft | null>(null)
export function setDraft(value: TemplateDraft | null) {
  if (draft.value && draft.value.preview !== value?.preview) URL.revokeObjectURL(draft.value.preview)
  draft.value = value
  if (!value) clearAllData()
}
export function clearDraft() { setDraft(null) }

// Keep the original view's field names at the boundary of the API draft.
type ViewLabel = Rect & {
  class: string; questionNo?: number; expectedAnswer?: string; answer?: string
  answerType?: AnswerType; answerTypeLocked?: boolean; confidence?: number
}
export function toViewLabel(label: Label): ViewLabel {
  return { ...label, class: label.label, expectedAnswer: label.answer, answer: '' }
}
export function toTemplateLabel(label: ViewLabel): Label {
  const answer = label.expectedAnswer ?? label.answer ?? ''
  return { ...label, label: label.class, answer, answerType: label.answerType ?? guessAnswerType(answer) }
}
export function openDraft(value: TemplateDraft) {
  setDraft(value)
  initializeFromUpload([], {
    name: value.name, preview: value.preview, labels: value.labels.map(toViewLabel),
    role: 'master', templateId: value.id, predictionsLoaded: !!value.id || value.labels.length > 0,
  })
}
