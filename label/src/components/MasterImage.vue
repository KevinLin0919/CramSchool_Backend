<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'
import { masterBlob } from '../templates'
const props = defineProps<{ id: number; name: string; width?: number }>()
const url = ref('')
const error = ref('')
let version = 0
function clear() { if (url.value) URL.revokeObjectURL(url.value); url.value = '' }
watch(() => [props.id, props.width], async () => {
  const request = ++version
  clear()
  error.value = ''
  try {
    const blob = await masterBlob(props.id, props.width)
    if (request === version) url.value = URL.createObjectURL(blob)
  } catch (err) {
    if (request === version) error.value = err instanceof Error ? err.message : '預覽載入失敗'
  }
}, { immediate: true })
onUnmounted(() => { version++; clear() })
</script>
<template><img v-if="url" :src="url" :alt="name" /><span v-else>{{ error || '載入預覽…' }}</span></template>
