import { useEffect, useSyncExternalStore } from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

// Toasts and a confirm dialog in place of alert/confirm, as the original
// editor had them. A small store so any handler can call them directly.

export type ToastType = "success" | "error" | "info";
type Toast = { id: number; type: ToastType; message: string };
export type ConfirmOptions = { title?: string; message: string; confirmText?: string; cancelText?: string; danger?: boolean };
type State = { toasts: Toast[]; confirm: (ConfirmOptions & { resolve: (ok: boolean) => void }) | null };

let state: State = { toasts: [], confirm: null };
let nextId = 1;
const listeners = new Set<() => void>();
const set = (next: Partial<State>) => { state = { ...state, ...next }; listeners.forEach((l) => l()); };

export function dismissToast(id: number) {
  set({ toasts: state.toasts.filter((t) => t.id !== id) });
}

export function showToast(message: string, type: ToastType = "info", duration = 3500) {
  const id = nextId++;
  set({ toasts: [...state.toasts, { id, type, message }] });
  setTimeout(() => dismissToast(id), duration);
}

/** Resolves true when the teacher confirms. */
export function askConfirm(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    state.confirm?.resolve(false);
    set({ confirm: { ...options, resolve } });
  });
}

function settle(ok: boolean) {
  const c = state.confirm;
  if (!c) return;
  set({ confirm: null });
  c.resolve(ok);
}

export function FeedbackHost() {
  const s = useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => state);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && state.confirm) settle(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <div className="toast-stack" aria-live="polite">
        {s.toasts.map((t) => (
          <div key={t.id} className={`toast toast--${t.type}`} role="status">
            {t.type === "success" ? <CheckCircle2 size={16} className="toast__icon" /> : t.type === "error" ? <AlertCircle size={16} className="toast__icon" /> : <Info size={16} className="toast__icon" />}
            <span className="toast__msg">{t.message}</span>
            <button className="toast__close" title="關閉" onClick={() => dismissToast(t.id)}><X size={13} /></button>
          </div>
        ))}
      </div>
      {s.confirm && (
        <div className="ds-modal-overlay confirm-overlay" onClick={(e) => { if (e.target === e.currentTarget) settle(false); }}>
          <div className="ds-modal confirm-modal" role="alertdialog" aria-modal="true">
            <div className="ds-modal__body confirm-body">
              {s.confirm.title && <h3>{s.confirm.title}</h3>}
              <p>{s.confirm.message}</p>
            </div>
            <div className="ds-modal__footer">
              <button className="ds-btn" onClick={() => settle(false)}>{s.confirm.cancelText || "取消"}</button>
              <button className={`ds-btn ${s.confirm.danger ? "ds-btn--danger" : "ds-btn--primary"}`} onClick={() => settle(true)}>{s.confirm.confirmText || "確認"}</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
