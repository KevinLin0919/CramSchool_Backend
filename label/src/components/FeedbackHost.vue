<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-vue-next'
import { useFeedback } from '../composables/useFeedback'

const { toasts, confirmState, dismissToast, settleConfirm } = useFeedback()

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && confirmState.visible) {
    settleConfirm(false)
  }
}

onMounted(() => window.addEventListener('keydown', handleKeydown))
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <Teleport to="body">
    <!-- Toast 通知 -->
    <div class="toast-stack" aria-live="polite">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="toast"
          :class="`toast--${t.type}`"
          role="status"
        >
          <CheckCircle2 v-if="t.type === 'success'" :size="16" class="toast__icon" />
          <AlertCircle v-else-if="t.type === 'error'" :size="16" class="toast__icon" />
          <Info v-else :size="16" class="toast__icon" />
          <span class="toast__msg">{{ t.message }}</span>
          <button class="toast__close" title="關閉" @click="dismissToast(t.id)">
            <X :size="13" />
          </button>
        </div>
      </TransitionGroup>
    </div>

    <!-- 確認對話框 -->
    <div
      v-if="confirmState.visible"
      class="ds-modal-overlay confirm-overlay"
      @click.self="settleConfirm(false)"
    >
      <div class="ds-modal confirm-modal" role="alertdialog" aria-modal="true">
        <div class="ds-modal__body confirm-body">
          <h3 v-if="confirmState.options.title">{{ confirmState.options.title }}</h3>
          <p>{{ confirmState.options.message }}</p>
        </div>
        <div class="ds-modal__footer">
          <button class="ds-btn" @click="settleConfirm(false)">
            {{ confirmState.options.cancelText || '取消' }}
          </button>
          <button
            class="ds-btn"
            :class="confirmState.options.danger ? 'ds-btn--danger' : 'ds-btn--primary'"
            @click="settleConfirm(true)"
          >
            {{ confirmState.options.confirmText || '確認' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 16px;
  right: 16px;
  z-index: 1100; /* 蓋在 modal（1000）之上 */
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: min(360px, calc(100vw - 32px));
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  font-size: var(--text-sm);
  color: var(--text-1);
}

.toast__icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.toast--success .toast__icon { color: var(--status-correct); }
.toast--error .toast__icon   { color: var(--status-wrong); }
.toast--info .toast__icon    { color: var(--accent); }

.toast--success { border-color: var(--status-correct-bg); }
.toast--error   { border-color: var(--status-wrong-bg); }

.toast__msg {
  flex: 1;
  line-height: var(--leading-normal);
  white-space: pre-line;
}

.toast__close {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
}

.toast__close:hover {
  background: var(--surface-hover);
  color: var(--text-1);
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--duration-base) var(--ease),
    transform var(--duration-base) var(--ease);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* 確認對話框 */
.confirm-modal {
  width: 420px;
}

.confirm-body h3 {
  margin: 0 0 8px;
  font-size: var(--text-md);
  font-weight: var(--weight-bold);
  color: var(--text-1);
}

.confirm-body p {
  margin: 0;
  color: var(--text-2);
  white-space: pre-line;
  line-height: var(--leading-normal);
}
</style>
