import { guessAnswerType, type AnswerType, type Label, type Rect, type TemplateDraft } from "./templates";

// The paper being edited, handed from the upload page to the editor. Its
// preview is an object URL, so replacing or dropping it frees the old one.
let current: TemplateDraft | null = null;

export function getDraft() { return current; }
export function setDraft(value: TemplateDraft | null) {
  if (current && current.preview !== value?.preview) URL.revokeObjectURL(current.preview);
  current = value;
}

// The editor's view of a cell, with the original editor's field names.
export type ViewLabel = Rect & {
  // Stable across edits: typing an answer makes a new object, not a new cell.
  uid: number;
  class: string; questionNo?: number; expectedAnswer: string;
  answerType: AnswerType; answerTypeLocked?: boolean; confidence?: number;
};
let nextUid = 1;
export const newUid = () => nextUid++;
export function toViewLabel(label: Label): ViewLabel {
  return { ...label, uid: newUid(), class: label.label, expectedAnswer: label.answer };
}
export function toTemplateLabel(label: ViewLabel): Label {
  const answer = label.expectedAnswer ?? "";
  return {
    x: label.x, y: label.y, width: label.width, height: label.height,
    questionNo: label.questionNo, answer, label: label.class, confidence: label.confidence,
    answerType: label.answerType ?? guessAnswerType(answer), answerTypeLocked: label.answerTypeLocked,
  };
}
