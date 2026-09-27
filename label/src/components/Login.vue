<script setup lang="ts">
import { ref } from 'vue'
import { BRAND, webLogin } from '../api'
const code = ref('')
const error = ref('')
const busy = ref(false)
async function submit() {
  if (busy.value || code.value.length !== 6) return
  busy.value = true
  error.value = ''
  try { await webLogin(code.value) } catch (err) {
    error.value = err instanceof Error ? err.message : '登入失敗'
  } finally { busy.value = false }
}
</script>

<template>
  <div class="login">
    <form class="ds-card" @submit.prevent="submit">
      <h1>{{ BRAND }}</h1><p>建立模板</p>
      <label for="code">登入碼</label>
      <input id="code" class="ds-input code" inputmode="numeric" autocomplete="one-time-code"
        maxlength="6" placeholder="000000" autofocus :value="code"
        @input="code = ($event.target as HTMLInputElement).value.replace(/\D/g, '').slice(0, 6)" />
      <p class="error" role="alert">{{ error }}</p>
      <button class="ds-btn ds-btn--primary" :disabled="code.length !== 6 || busy">{{ busy ? '登入中…' : '登入' }}</button>
      <p>在手機 App 的「設定 → 在電腦上看報告」取得 6 位數登入碼。</p>
    </form>
  </div>
</template>

<style scoped>
.login { min-height: 75vh; display: grid; place-items: center; padding: 20px; }
form { width: min(380px, 100%); padding: 32px 28px; display: flex; flex-direction: column; gap: 10px; }
h1 { font-weight: 700; text-align: center; }
.code { font-size: 32px; letter-spacing: .35em; text-align: center; }
p { font-size: 13px; color: var(--text-2); }
.error { min-height: 20px; color: var(--danger); }
</style>
