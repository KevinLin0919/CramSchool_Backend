import { reactive } from 'vue'

// 全域回饋機制：toast 通知＋確認對話框（取代原生 alert / confirm）

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: number
  type: ToastType
  message: string
}

const toasts = reactive<Toast[]>([])
let nextToastId = 1

export const dismissToast = (id: number) => {
  const index = toasts.findIndex((t) => t.id === id)
  if (index !== -1) toasts.splice(index, 1)
}

export const showToast = (message: string, type: ToastType = 'info', duration = 3500) => {
  const id = nextToastId++
  toasts.push({ id, type, message })
  setTimeout(() => dismissToast(id), duration)
}

export interface ConfirmOptions {
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  danger?: boolean
}

interface ConfirmState {
  visible: boolean
  options: ConfirmOptions
  resolve: ((ok: boolean) => void) | null
}

const confirmState = reactive<ConfirmState>({
  visible: false,
  options: { message: '' },
  resolve: null,
})

/** 顯示確認對話框，回傳使用者是否按下確認 */
export const askConfirm = (options: ConfirmOptions) => {
  return new Promise<boolean>((resolve) => {
    // 若前一個對話框尚未關閉，視為取消
    confirmState.resolve?.(false)
    confirmState.options = options
    confirmState.visible = true
    confirmState.resolve = resolve
  })
}

export const settleConfirm = (ok: boolean) => {
  if (!confirmState.visible) return
  confirmState.visible = false
  confirmState.resolve?.(ok)
  confirmState.resolve = null
}

export const useFeedback = () => ({
  toasts,
  confirmState,
  showToast,
  dismissToast,
  askConfirm,
  settleConfirm,
})
