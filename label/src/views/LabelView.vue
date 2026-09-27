<template>
  <div class="label-container">

    <div v-if="!hasAnyImages" class="ds-card no-images">
      <p>尚未上傳圖片，請先完成上傳。</p>
      <button @click="goToUpload" class="ds-btn ds-btn--primary">前往上傳</button>
    </div>

    <div v-else class="labeling-workspace">
      <!-- 側欄：考卷列表 -->
      <aside class="ds-card sidebar">
        <div class="ds-segmented ds-segmented--sm view-toggle">
          <button
            type="button"
            class="ds-segmented__btn"
            :class="{ 'is-active': viewMode === 'master' }"
            @click="viewMode = 'master'"
          >
            答案卷
          </button>
        </div>
        <div class="image-list">
          <div
            v-for="(img, index) in displayedImages"
            :key="index"
            class="image-list-item"
            :class="{ active: currentImageIndex === index }"
            @click="selectImage(index)"
          >
            <img v-if="img.preview" :src="img.preview" :alt="img.name" class="thumb" />
            <span v-else class="thumb thumb--empty"></span>
            <span class="item-text">
              <span class="item-name">{{ img.name }}</span>
              <span class="item-count">{{ img.labels?.length || 0 }} 個標註</span>
            </span>
          </div>
        </div>
      </aside>

      <!-- 畫布區 -->
      <section class="ds-card canvas-card">
        <div class="canvas-toolbar">
          <div class="ds-segmented ds-segmented--sm">
            <button
              type="button"
              class="ds-segmented__btn"
              :class="{ 'is-active': currentMode === 'draw' }"
              :disabled="locked"
              @click="currentMode = 'draw'"
            >
              <Crosshair :size="14" /> 標註
            </button>
            <button
              type="button"
              class="ds-segmented__btn"
              :class="{ 'is-active': currentMode === 'pan' }"
              @click="currentMode = 'pan'"
            >
              <Move :size="14" /> 拖移
            </button>
          </div>
          <button class="ds-btn ds-btn--sm" :class="{ 'ds-btn--primary': currentMode === 'name' }" :disabled="locked" @click="currentMode = 'name'">
            <UserRound :size="14" /> 框姓名欄
          </button>
          <span class="toolbar-hint">拖移可按住 Ctrl</span>
          <span class="spacer"></span>
          <button class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" @click="changeZoom(-0.1)" title="縮小">
            <ZoomOut :size="14" />
          </button>
          <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
          <button class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" @click="changeZoom(0.1)" title="放大">
            <ZoomIn :size="14" />
          </button>
          <button class="ds-btn ds-btn--ghost ds-btn--sm" @click="resetView">重置</button>
        </div>

        <div class="canvas-area">
          <canvas
            ref="canvas"
            tabindex="0"
            :style="{
              cursor: getCursorStyle(),
              outline: 'none' /* 移除聚焦時的預設黑框 */
            }"
            @mousedown="startDrawing"
            @mousemove="draw"
            @mouseup="endDrawing"
            @mouseleave="endDrawing"
            @wheel.prevent="handleWheel"
          ></canvas>
        </div>

        <div class="canvas-footer">
          <template v-if="currentImage">
            <span v-if="currentImage.isPredicting" class="ds-badge ds-badge--pending">
              <Clock :size="11" /> 偵測中…
            </span>
            <template v-else-if="currentImage.predictionError">
              <span class="ds-badge ds-badge--wrong">
                <X :size="11" /> {{ currentImage.predictionError }}
              </span>
              <button @click="retryPrediction" :disabled="locked" class="ds-btn ds-btn--ghost ds-btn--sm">重試</button>
            </template>
            <span v-else-if="currentImage.predictionsLoaded && !draft?.id && !(currentImage.labels?.length)" class="ds-badge ds-badge--pending">
              沒有偵測到答案格，請在圖上手動框選
            </span>
            <span v-else-if="currentImage.predictionsLoaded" class="ds-badge ds-badge--correct">
              <Check :size="11" /> {{ draft?.id ? '已載入模板' : '已套用偵測結果' }}
            </span>
            <span v-else class="ds-badge">等待偵測</span>
          </template>
          <span class="spacer"></span>
          <button
            @click="previousImage"
            :disabled="currentImageIndex === 0"
            class="ds-btn ds-btn--ghost ds-btn--sm"
          >
            <ChevronLeft :size="14" /> 上一張
          </button>
          <span class="image-counter">{{ currentImageIndex + 1 }} / {{ displayedImages.length }}</span>
          <button
            @click="nextImage"
            :disabled="currentImageIndex === displayedImages.length - 1"
            class="ds-btn ds-btn--ghost ds-btn--sm"
          >
            下一張 <ChevronRight :size="14" />
          </button>
        </div>
      </section>

      <!-- 右欄：標註面板 -->
      <aside class="side-panel">
        <div class="ds-card panel-card">
          <p class="ds-eyebrow panel-label">考卷資訊</p>
          <div v-if="draft" class="template-fields">
            <label class="hint-text">考卷名稱<input v-model="draft.name" class="ds-input ds-input--sm" maxlength="255" :disabled="locked" /></label>
            <label class="hint-text">單元<input v-model="draft.unit" class="ds-input ds-input--sm" maxlength="40" placeholder="選填，最多 40 字" :disabled="locked" /></label>
            <label class="hint-text">選項數<input v-model.number="draft.optionCount" class="ds-input ds-input--sm ds-input--mono" type="number" min="2" max="10" step="1" :disabled="locked" /></label>
          </div>
          <p v-if="readOnly" class="ds-banner ds-banner--warning">這份考卷有多頁，網頁目前只能檢視第一頁</p>
          <p v-if="invalidMetadata" class="hint-text field-error">請填入考卷名稱，單元最多 40 字，選項數須為 2–10。</p>
          <p class="ds-eyebrow panel-label">工具</p>
          <div class="batch-grid">
            <button
              @click="retryPrediction"
              :disabled="locked"
              class="ds-btn ds-btn--sm"
            >
              <RotateCw :size="14" /> 重新偵測
            </button>
            <button
              @click="autoSort"
              :disabled="locked || !currentImage?.labels || currentImage.labels.length === 0"
              class="ds-btn ds-btn--sm"
            >
              <ArrowUpDown :size="14" /> 自動排序
            </button>
          </div>
          <div v-if="draft?.nameBox" class="class-row">
            <span class="ds-badge">已框選姓名欄</span>
            <button class="ds-btn ds-btn--danger ds-btn--sm" :disabled="locked" @click="removeNameBox">刪除姓名框</button>
          </div>
        </div>

        <div class="ds-card panel-card">
          <p class="ds-eyebrow panel-label">目前標註（{{ currentImage?.labels?.length || 0 }}）</p>
          <div v-if="currentImage?.labels && currentImage.labels.length > 0 && isMasterView" class="batch-bar">
            <label class="batch-all hint-text">
              <input type="checkbox" :checked="allChecked" :indeterminate="checked.length > 0 && !allChecked" :disabled="locked" @change="toggleAll" />
              {{ checked.length ? `已選 ${checked.length} 格` : '全選' }}
            </label>
            <select v-model="batchType" class="ds-input ds-input--sm" :disabled="locked || !checked.length" aria-label="整批設定題型">
              <option value="choice">選擇題</option><option value="mark">是非題</option><option value="digit">填空題</option>
            </select>
            <button class="ds-btn ds-btn--sm" :disabled="locked || !checked.length" @click="applyBatchType">套用題型</button>
          </div>
          <p v-if="currentImage?.labels?.length && isMasterView" class="hint-text batch-hint">勾選要設定的格子，按住 Shift 可一次勾選一整段。</p>
          <div v-if="currentImage?.labels && currentImage.labels.length > 0" class="label-scroll">
            <div
              v-for="(label, index) in currentImage.labels"
              :key="index"
              class="label-item"
              :class="{ 'selected': index === selectedLabelIndex, 'invalid': labelError(label) }"
              @click="isMasterView ? focusLabelInput(index) : selectLabel(index)"
            >
              <input v-if="isMasterView" type="checkbox" class="label-check" :checked="checked.includes(label)" :disabled="locked"
                :aria-label="`勾選第 ${questionNumbers.get(label)} 題`" @click.stop="toggleCheck(index, $event)" />
              <span class="label-index">#{{ questionNumbers.get(label) }}</span>
              <span class="label-name">{{ label.class }}</span>

              <span v-if="isMasterView" class="label-expected">
                <span class="input-prefix">正解</span>
                <input
                  type="text"
                  v-model="label.expectedAnswer"
                  :disabled="locked"
                  :aria-invalid="!!labelError(label)"
                  :title="labelError(label)"
                  :placeholder="({ choice: '例：B 或 2', mark: '○ 或 ✕', digit: '數字' } as Record<string, string>)[label.answerType ?? ''] ?? ''"
                  @input="inferAnswerType(label)"
                  class="ds-input ds-input--sm ds-input--mono expected-value"
                  :ref="(el) => { if(el) inputRefs[index] = el as HTMLInputElement }"
                  @focus="selectLabel(index)"
                  @keydown="handleInputKeydown(index, $event)"
                  @click.stop
                />
              </span>

              <button @click.stop="removeLabel(index)" :disabled="locked" class="ds-btn ds-btn--ghost ds-btn--sm ds-btn--icon" title="刪除標註">
                <X :size="14" />
              </button>
              <label class="label-type hint-text">題型
                <select v-model="label.answerType" class="ds-input ds-input--sm" :disabled="locked" @change="label.answerTypeLocked = true" @click.stop>
                  <option value="choice">選擇題</option><option value="mark">是非題</option><option value="digit">填空題</option>
                  <option v-if="!['choice', 'mark', 'digit'].includes(label.answerType ?? '')" :value="label.answerType">其他</option>
                </select>
              </label>
              <p v-if="labelError(label)" class="hint-text field-error" role="alert">{{ labelError(label) }}</p>
            </div>
          </div>
          <p v-else class="no-labels">尚無標註，請在圖上拖曳畫框。</p>
        </div>

        <div class="ds-card ds-card--sunken panel-card">
          <div class="panel-actions">
            <button @click="clearLabels" :disabled="locked" class="ds-btn ds-btn--danger ds-btn--sm">清除標註</button>
          </div>
          <p v-if="saveError" class="ds-banner ds-banner--danger" role="alert">{{ saveError }}
            <button v-if="draft?.id" class="ds-btn ds-btn--sm" @click="reloadTemplate">重新載入</button>
          </p>
          <button @click="saveCurrentTemplate" :disabled="locked || invalidAnswers || invalidMetadata || !hasAnswers" class="ds-btn ds-btn--primary results-btn">
            <Save :size="16" /> {{ saving ? '儲存中…' : '儲存模板' }}
          </button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, onBeforeUpdate, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Crosshair, Move, ZoomIn, ZoomOut, ChevronLeft, ChevronRight,
  RotateCw, ArrowUpDown, X, Check, Clock,
  Save, UserRound,
} from 'lucide-vue-next'
import { CANVAS_WIDTH, CANVAS_HEIGHT } from '../constants'
import { getStoreData, hasData, updateMasterImage } from '../stores/resultsStore'
import { showToast, askConfirm } from '../composables/useFeedback'
import { apiFetch } from '../api'
import { toBase64 } from '../imaging'
import { answerError, guessAnswerType, mergeDetections, readTemplate, saveTemplate, sortLabels, type AnswerType } from '../templates'
import { draft, clearDraft, openDraft, toViewLabel, toTemplateLabel } from '../stores/templateStore'

const DEFAULT_CLASS = '答案區'

interface Label {
  questionNo?: number
  answerType?: AnswerType
  answerTypeLocked?: boolean
  class: string
  x: number
  y: number
  width: number
  height: number
  // YOLO 回傳的信心值，用來比較不同影像的偵測品質
  confidence?: number
  recognizedAnswer?: string
  answer?: string
  expectedAnswer?: string
  isCorrect?: boolean
  // [新增] 用來暫存後端回傳的兩種結果
  ocrCandidates?: {
    chinese: string
    digit: string
  }
}

interface ImageData {
  name: string
  preview: string
  labels?: Label[]
  predictionsLoaded?: boolean
  isPredicting?: boolean
  predictionError?: string
  role: 'student' | 'master'
  // 答案卷來自已儲存模板時的模板 id，用來判斷該新增還是更新模板
  templateId?: number | null
}

const draggingLabelIndex = ref<number>(-1) // 記錄正在拖曳的標籤索引
const dragOffset = ref({ x: 0, y: 0 })     // 記錄點擊點與框框左上角的距離
const hoverLabelIndex = ref<number>(-1)    // 記錄滑鼠目前懸停在哪個框上 (用來變更游標)
const router = useRouter()
const route = useRoute()
let active = true
let paintVersion = 0
const canvas = ref<HTMLCanvasElement | null>(null)
const studentImages = ref<ImageData[]>([])
const masterKeyImage = ref<ImageData | null>(null)
const viewMode = ref<'student' | 'master'>('master')
const currentImageIndex = ref(0)
const currentClass = ref(DEFAULT_CLASS)
const isDrawing = ref(false)
const isPanning = ref(false)
const currentMode = ref<'draw' | 'pan' | 'name'>('draw')
const isCtrlPressed = ref(false) // 追蹤 Ctrl 鍵狀態
const startX = ref(0)
const startY = ref(0)
const currentX = ref(0)
const currentY = ref(0)
const panX = ref(0)
const panY = ref(0)
const zoom = ref(1)

const selectedLabelIndex = ref<number>(-1)
const inputRefs = ref<HTMLInputElement[]>([])
const saving = ref(false)
const saveError = ref('')
const readOnly = computed(() => (draft.value?.pageCount ?? 0) > 1)
const locked = computed(() => readOnly.value || saving.value || !!currentImage.value?.isPredicting)
const labelError = (label: Label) => answerError(toTemplateLabel(label), draft.value?.optionCount ?? 4)
const invalidAnswers = computed(() => !!currentImage.value?.labels?.some(label => labelError(label)))
const hasAnswers = computed(() => !!currentImage.value?.labels?.some(label => label.expectedAnswer?.trim()))
const invalidMetadata = computed(() => !draft.value?.name.trim() || Array.from(draft.value.unit).length > 40 ||
  !Number.isInteger(draft.value.optionCount) || draft.value.optionCount < 2 || draft.value.optionCount > 10)
const questionNumbers = computed(() => {
  const labels = currentImage.value?.labels ?? []
  const value = draft.value
  const numbers = new Map<Label, number>()
  if (!value) return numbers
  let next = Math.max(value.maxQuestionNo, ...labels.map(label => label.questionNo ?? 0))
  sortLabels(labels, value.width, value.height).forEach((label, index) => {
    numbers.set(label, value.id ? label.questionNo ?? ++next : index + 1)
  })
  return numbers
})
const inferAnswerType = (label: Label) => {
  if (!label.answerTypeLocked) {
    label.answerType = guessAnswerType(label.expectedAnswer ?? '', draft.value?.optionCount ?? 4)
  }
}

const displayedImages = computed(() =>
  viewMode.value === 'student'
    ? studentImages.value
    : masterKeyImage.value
      ? [masterKeyImage.value]
      : []
)
const currentImage = computed(() => displayedImages.value[currentImageIndex.value])

// A lone "2" is an option only while it is within the option count, so a
// change there re-reads every cell the teacher has not set by hand.
watch(() => draft.value?.optionCount, () => {
  currentImage.value?.labels?.forEach(inferAnswerType)
})

// Batch typing. The detector finds cells but not what kind of question each
// one is, so the teacher ticks a run of cells and sets the type once.
const checked = ref<Label[]>([])
const batchType = ref<AnswerType>('choice')
let lastChecked = -1
const allChecked = computed(() => {
  const labels = currentImage.value?.labels ?? []
  return labels.length > 0 && labels.every(label => checked.value.includes(label))
})
const toggleAll = () => {
  checked.value = allChecked.value ? [] : [...(currentImage.value?.labels ?? [])]
}
const toggleCheck = (index: number, event: MouseEvent) => {
  const labels = currentImage.value?.labels ?? []
  const label = labels[index]
  if (!label) return
  const on = !checked.value.includes(label)
  const range = event.shiftKey && lastChecked >= 0
    ? labels.slice(Math.min(lastChecked, index), Math.max(lastChecked, index) + 1)
    : [label]
  checked.value = on
    ? [...checked.value, ...range.filter(l => !checked.value.includes(l))]
    : checked.value.filter(l => !range.includes(l))
  lastChecked = index
}
const applyBatchType = () => {
  checked.value.forEach(label => { label.answerType = batchType.value; label.answerTypeLocked = true })
  showToast(`已將 ${checked.value.length} 格設為「${({ choice: '選擇題', mark: '是非題', digit: '填空題' } as Record<string, string>)[batchType.value]}」`, 'success')
  checked.value = []
}
// Removed or re-detected cells must not linger in the selection.
watch(() => currentImage.value?.labels, labels => {
  checked.value = checked.value.filter(l => labels?.includes(l))
}, { deep: false })
const isMasterView = computed(() => viewMode.value === 'master')
const hasAnyImages = computed(() => studentImages.value.length > 0 || !!masterKeyImage.value)

// 確保在列表更新前清空 refs
onBeforeUpdate(() => {
  inputRefs.value = []
})

// 監聽 Ctrl 鍵狀態
const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key === 'Control') {
    isCtrlPressed.value = true
  }
}
const handleKeyUp = (event: KeyboardEvent) => {
  if (event.key === 'Control') {
    isCtrlPressed.value = false
  }
}

onMounted(async () => {
  // 註冊全域鍵盤監聽
  window.addEventListener('keydown', handleGlobalKeydown)
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)

  const id = Number(route.params.id)
  if (id && id !== draft.value?.id) {
    try {
      const value = await readTemplate(id)
      if (!active) { URL.revokeObjectURL(value.preview); return }
      openDraft(value)
    } catch (error) {
      if (active) showToast(error instanceof Error ? error.message : '載入模板失敗', 'error')
      return
    }
  }

  // 從統一的 store 讀取資料
  if (hasData()) {
    const { studentImages: storedStudents, masterKeyImage: storedMaster } = getStoreData()

    if (storedStudents.length > 0) {
      studentImages.value = storedStudents.map((f: any) => ({
        ...f,
        labels: f.labels || [],
        preview: f.preview,
        predictionsLoaded: f.predictionsLoaded || false,
        isPredicting: false,
        predictionError: undefined,
        role: 'student'
      }))
    }

    if (storedMaster) {
      masterKeyImage.value = {
        ...storedMaster,
        labels: storedMaster.labels || [],
        preview: storedMaster.preview,
        predictionsLoaded: storedMaster.predictionsLoaded || false,
        isPredicting: false,
        predictionError: undefined,
        role: 'master'
      }
    }
  }
  currentImageIndex.value = 0

  // 先顯示圖片
  nextTick(() => {
    handleImageChange()
  })

  // 檢查是否已經有標註資料（例如從 ResultsView 返回）
  const hasExistingLabels = studentImages.value.some(img => img.labels && img.labels.length > 0) ||
    (masterKeyImage.value?.labels && masterKeyImage.value.labels.length > 0)

  // 只有在沒有現有標註時才執行初始 YOLO 偵測
  if (!hasExistingLabels && !draft.value?.id && !readOnly.value) {
    await runInitialDetection()
  }
});

// 只複製框的位置，不帶走作答內容
const cloneLabelsAsBlank = (labels: Label[]): Label[] =>
  labels.map(label => ({
    ...label,
    answer: '',
    recognizedAnswer: undefined,
    expectedAnswer: undefined,
    ocrCandidates: undefined,
    isCorrect: undefined
  }))

// 偵測品質評分：以高信心框的數量為準，總框數作為平手時的次要依據。
// 低信心的框多半是誤判，全部一起算會讓雜訊多的那張反而勝出。
const HIGH_CONFIDENCE = 0.8

const scoreDetection = (labels?: Label[]) => {
  if (!labels || labels.length === 0) return { high: 0, total: 0 }
  const high = labels.filter(l => (l.confidence ?? 1) >= HIGH_CONFIDENCE).length
  return { high, total: labels.length }
}

/**
 * 初始偵測：答案卷與第一張學生卷各偵測一次，採用結果較好的那一份，
 * 再把框套用到批次內所有影像。
 *
 * 兩張影像雖然版面相同，但往往是不同來源（答案卷可能是教師用的電子檔，
 * 學生卷則是掃描或影印），清晰度可能差距很大——實測同一份考卷，
 * 乾淨的答案卷可偵測到 22 格，影印的學生卷只有 9 格。
 * 固定只跑兩次推論，與班級人數無關，仍遠低於逐張偵測的成本。
 */
const runInitialDetection = async () => {
  const master = masterKeyImage.value
  const firstStudent = studentImages.value[0]

  // 答案卷排在前面，平手時即優先採用（正解讀取需要框與答案卷對齊）
  const candidates: ImageData[] = [master, firstStudent].filter(
    (img): img is ImageData => !!img && !!img.preview
  )

  if (candidates.length === 0) return

  for (const img of candidates) {
    await fetchPredictionsForImage(img)
  }

  // 挑出偵測品質最好的來源
  let source: ImageData | null = null
  let bestScore = { high: -1, total: -1 }
  for (const img of candidates) {
    const s = scoreDetection(img.labels)
    if (s.high > bestScore.high || (s.high === bestScore.high && s.total > bestScore.total)) {
      source = img
      bestScore = s
    }
  }

  if (!source) return

  if (!source.labels || source.labels.length === 0) return

  // 依版面方向排序，使題號順序符合閱讀順序
  const previewImg = await loadPreviewImage(source.preview)
  const isVertical = previewImg.height > previewImg.width
  source.labels = isVertical
    ? sortLabelsVertical(source.labels)
    : sortLabelsRightToLeft(source.labels)

  const sourceLabels = source.labels

  if (master && master !== source) {
    master.labels = cloneLabelsAsBlank(sourceLabels)
    master.predictionsLoaded = true
    master.predictionError = undefined
  }

  studentImages.value.forEach(student => {
    if (student === source) return
    student.labels = cloneLabelsAsBlank(sourceLabels)
    student.predictionsLoaded = true
    student.predictionError = undefined
  })

  loadImage()
}

onUnmounted(() => {
  active = false
  paintVersion++
  if (draft.value && masterKeyImage.value) {
    draft.value.labels = (masterKeyImage.value.labels ?? []).map(toTemplateLabel)
    masterKeyImage.value.name = draft.value.name
    updateMasterImage(masterKeyImage.value)
  }
  window.removeEventListener('keydown', handleGlobalKeydown)
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
})

watch(currentImageIndex, () => {
  handleImageChange()
})

watch(viewMode, () => {
  currentImageIndex.value = 0
  nextTick(() => {
    handleImageChange()
  })
})

const getCursorStyle = () => {
  const isPanMode = currentMode.value === 'pan' || isCtrlPressed.value

  // 正在拖曳中
  if (isPanning.value || draggingLabelIndex.value !== -1) {
    return 'grabbing'
  }

  // 拖移模式下，hover 在框框上顯示小手
  if (isPanMode && hoverLabelIndex.value !== -1) {
    return 'grab'
  }

  // 拖移模式下，空白處顯示小手
  if (isPanMode) {
    return 'grab'
  }

  // 標註模式，一律顯示十字
  return 'crosshair'
}

// [修改] 改名為 runOCRForImage，並接受參數，讓它可以處理任何一張圖
const extractTextValue = (value: any, seen = new Set<any>()): string => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim()
  }
  if (Array.isArray(value)) {
    return value.length > 0 ? extractTextValue(value[0], seen) : ''
  }
  if (typeof value === 'object') {
    if (seen.has(value)) return ''
    seen.add(value)
    const candidate =
      value.text ??
      value.words ??
      value.word ??
      value.label ??
      value.content ??
      value.result ??
      value.prediction ??
      value.ocr ??
      value.value ??
      value.answer ??
      value.recognizedAnswer ??
      value.data?.text ??
      value.data?.words ??
      value.data?.word ??
      value.data?.label ??
      value.data?.result ??
      value.data?.prediction ??
      value.data?.ocr
    if (candidate !== undefined && candidate !== null) {
      return candidate === value ? '' : extractTextValue(candidate, seen)
    }
    for (const key of Object.keys(value)) {
      const found = extractTextValue((value as Record<string, any>)[key], seen)
      if (found) return found
    }
  }
  return ''
}

const chooseOcrValue = (res: { chinese?: string; digit?: string } | string) => {
  if (typeof res === 'string') return res.trim()
  const digit = String(res.digit || '').trim()
  const chinese = String(res.chinese || '').trim()
  return digit || chinese
}

const handleImageChange = () => {
  selectedLabelIndex.value = -1
  inputRefs.value = []
  panX.value = 0
  panY.value = 0
  zoom.value = 1
  if (currentImage.value) {
    currentImage.value.predictionError = undefined
    if (!currentImage.value.labels) currentImage.value.labels = []
  }
  loadImage()
  if (currentImage.value?.role === 'student') {
    fetchPredictionsForCurrentImage()
  }
}

// 全域鍵盤事件：處理非輸入框焦點時的刪除
const handleGlobalKeydown = (event: KeyboardEvent) => {
  if (locked.value || selectedLabelIndex.value === -1) return

  if (event.key === 'Backspace' || event.key === 'Delete') {
    const activeEl = document.activeElement as HTMLElement

    // 如果焦點正在輸入框內，不執行這裡的邏輯 (交給 handleInputKeydown)
    if (activeEl instanceof HTMLInputElement || activeEl instanceof HTMLTextAreaElement || activeEl instanceof HTMLSelectElement || activeEl?.isContentEditable) {
      return
    }

    event.preventDefault()
    removeLabel(selectedLabelIndex.value)
  }
}

const computeFit = (imgWidth: number, imgHeight: number) => {
  const scale = Math.min(CANVAS_WIDTH / imgWidth, CANVAS_HEIGHT / imgHeight)
  const offsetX = (CANVAS_WIDTH - imgWidth * scale) / 2
  const offsetY = (CANVAS_HEIGHT - imgHeight * scale) / 2

  return { scale, offsetX, offsetY }
}

// [新增] 根據輸入的答案，自動選擇要採信 OCR 的中文還是數字結果
const updateRecognizedAnswer = (label: Label) => {
  // 如果沒有候選資料，就跳過
  if (!label.ocrCandidates) return

  const input = label.answer ? label.answer.trim() : ''

  // 判斷邏輯：如果是純數字 (RegExp: ^\d+$)，就選 digit，否則選 chinese
  // 你也可以改用 /[0-9]/.test(input) 只要包含數字就切換，視你的需求而定
  const isDigit = /^\d+$/.test(input)

  if (isDigit) {
    label.recognizedAnswer = label.ocrCandidates.digit
  } else {
    label.recognizedAnswer = label.ocrCandidates.chinese
  }
}

const loadPreviewImage = (preview: string) => {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = preview
  })
}

const loadImage = () => {
  if (!canvas.value || !currentImage.value) return

  const ctx = canvas.value.getContext('2d')
  if (!ctx) return

  const request = ++paintVersion
  const img = new Image()
  img.onload = () => {
    if (!active || !canvas.value || request !== paintVersion) return
    canvas.value!.width = CANVAS_WIDTH
    canvas.value!.height = CANVAS_HEIGHT
    ctx.clearRect(0, 0, canvas.value!.width, canvas.value!.height)

    const fit = computeFit(img.width, img.height)

    ctx.save()
    ctx.setTransform(zoom.value, 0, 0, zoom.value, panX.value, panY.value)
    ctx.drawImage(img, fit.offsetX, fit.offsetY, img.width * fit.scale, img.height * fit.scale)

    drawLabels(ctx)
    ctx.restore()
  }

  if (currentImage.value.preview) {
    img.src = currentImage.value.preview
  } else {
    canvas.value.width = CANVAS_WIDTH
    canvas.value.height = CANVAS_HEIGHT
    ctx.fillStyle = '#f0f0f0'
    ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT)
    ctx.fillStyle = '#666'
    ctx.font = '24px "Noto Sans TC", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('沒有可顯示的圖片', CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2)
  }
}

const drawLabels = (ctx: CanvasRenderingContext2D) => {
  if (!canvas.value || !currentImage.value?.labels) return

  currentImage.value.labels.forEach((label, index) => {
    const isSelected = index === selectedLabelIndex.value
    const colors = getComputedStyle(canvas.value!)
    ctx.strokeStyle = colors.getPropertyValue(isSelected ? '--danger' : '--accent').trim()
    ctx.lineWidth = isSelected ? 3 : 2
    ctx.strokeRect(label.x, label.y, label.width, label.height)
  })
  const nameBox = draft.value?.nameBox
  ctx.strokeStyle = getComputedStyle(canvas.value).getPropertyValue('--name-box').trim()
  ctx.lineWidth = 2
  if (nameBox) {
    ctx.strokeRect(nameBox.x, nameBox.y, nameBox.width, nameBox.height)
    ctx.fillStyle = ctx.strokeStyle
    ctx.font = '13px "Noto Sans TC", sans-serif'
    ctx.fillText('姓名', nameBox.x, nameBox.y - 4)
  }
  if (isDrawing.value) {
    if (currentMode.value !== 'name') ctx.strokeStyle = getComputedStyle(canvas.value).getPropertyValue('--danger').trim()
    ctx.strokeRect(startX.value, startY.value, currentX.value - startX.value, currentY.value - startY.value)
  }
}

const focusLabelInput = (index: number) => {
  nextTick(() => {
    const inputEl = inputRefs.value[index]
    if (inputEl) {
      inputEl.focus()
    }
  })
}

const selectLabel = (index: number) => {
  if (selectedLabelIndex.value !== index) {
    selectedLabelIndex.value = index
    loadImage()
  }
}

// [修改] 處理輸入框按鍵事件：Enter 跳轉 & Backspace 刪除
const handleInputKeydown = (index: number, event: KeyboardEvent) => {
  if (locked.value) return
  const label = currentImage.value?.labels?.[index]
  if (!label) return
  const inputValue = isMasterView.value ? label.expectedAnswer : label.answer

  // 1. Enter 鍵 -> 跳到下一個輸入框
  if (event.key === 'Enter') {
    event.preventDefault()
    // 檢查是否有下一個標籤
    const nextIndex = index + 1
    if (currentImage.value?.labels && nextIndex < currentImage.value.labels.length) {
      focusLabelInput(nextIndex)
    }
    return
  }

  // 2. Backspace/Delete 鍵 -> 如果是空的則刪除框框
  if ((event.key === 'Backspace' || event.key === 'Delete') && (inputValue ?? '') === '') {
    event.preventDefault()
    removeLabel(index)
  }
}

const startDrawing = (event: MouseEvent) => {
  if (!canvas.value || event.button !== 0) return
  if (locked.value) { startPan(event); return }

  // 判斷是否為拖移模式（拖移按鈕選中 或 按住 Ctrl）
  const isPanMode = currentMode.value === 'pan' || event.ctrlKey

  const { x, y } = getCanvasCoords(event)
  const labels = currentImage.value?.labels || []

  // 檢查是否點擊在現有的框框上
  let hitIndex = -1
  for (let i = labels.length - 1; i >= 0 && (currentMode.value !== 'name' || isPanMode); i--) {
    const l = labels[i]
    if (!l) continue
    if (x >= l.x && x <= l.x + l.width && y >= l.y && y <= l.y + l.height) {
      hitIndex = i
      break
    }
  }

  // === 拖移模式 ===
  if (isPanMode) {
    if (hitIndex !== -1) {
      // 點到框框 → 移動框框
      draggingLabelIndex.value = hitIndex
      selectedLabelIndex.value = hitIndex
      const targetLabel = labels[hitIndex]
      if (targetLabel) {
        dragOffset.value = {
          x: x - targetLabel.x,
          y: y - targetLabel.y
        }
      }
      focusLabelInput(hitIndex)
      loadImage()
    } else {
      // 點到空白處 → 移動畫布
      startPan(event)
    }
    return
  }

  // === 標註模式 ===
  // 點到框框 → 選取該框框（不移動）
  if (hitIndex !== -1) {
    selectedLabelIndex.value = hitIndex
    focusLabelInput(hitIndex)
    loadImage()
    return
  }

  // 點到空白處 → 清除選取並開始畫新框
  if (selectedLabelIndex.value !== -1) {
    selectedLabelIndex.value = -1
    loadImage()
  }

  startX.value = currentX.value = x
  startY.value = currentY.value = y
  isDrawing.value = true
}

const draw = (event: MouseEvent) => {
  const { x, y } = getCanvasCoords(event)

  if (isPanning.value) {
    handlePanMove(event)
    return
  }

  if (locked.value) return

  // [修正] 拖曳框框的邏輯
  if (draggingLabelIndex.value !== -1 && currentImage.value?.labels) {
    const label = currentImage.value.labels[draggingLabelIndex.value]
    // [修正] 確保 label 存在才執行
    if (label) {
      label.x = x - dragOffset.value.x
      label.y = y - dragOffset.value.y
      loadImage()
    }
    return
  }

  // [修正] 滑鼠懸停 (Hover) 效果的邏輯
  if (!isDrawing.value && draggingLabelIndex.value === -1) {
    const labels = currentImage.value?.labels || []
    let found = -1
    for (let i = labels.length - 1; i >= 0; i--) {
      const l = labels[i]
      // [修正] 加入 undefined 檢查
      if (!l) continue

      if (x >= l.x && x <= l.x + l.width && y >= l.y && y <= l.y + l.height) {
        found = i
        break
      }
    }
    if (hoverLabelIndex.value !== found) {
      hoverLabelIndex.value = found
    }
  }

  // 畫新框邏輯 (保持原樣)
  if (!isDrawing.value || !canvas.value) return

  currentX.value = x
  currentY.value = y

  loadImage()

}

// [新增] 通用函數：對任意圖片執行 YOLO 偵測
const fetchPredictionsForImage = async (img: ImageData) => {
  if (!draft.value || readOnly.value || saving.value || !img || !img.preview || img.isPredicting || img.predictionsLoaded) return

  img.isPredicting = true
  img.predictionError = undefined

  try {
    const previewImg = await loadPreviewImage(img.preview)
    const { scale, offsetX, offsetY } = computeFit(previewImg.width, previewImg.height)
    const image_base64 = await toBase64(draft.value.blob)
    const response = await apiFetch('/api/v1/templates/detect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ image_base64 })
    })

    if (!response.ok) {
      throw new Error(`Prediction failed with status ${response.status}`)
    }

    const data = await response.json()
    const detections = data?.detections || data?.body?.json?.detections || []

    const mappedLabels: Label[] = detections.map((detection: any) => {
      const bbox = detection?.bbox || []
      const [x1, y1, x2, y2] = bbox
      const normalizedX1 = Number(x1) || 0
      const normalizedY1 = Number(y1) || 0
      const normalizedX2 = Number(x2) || 0
      const normalizedY2 = Number(y2) || 0

      const boxX = Math.max(0, normalizedX1 * scale + offsetX)
      const boxY = Math.max(0, normalizedY1 * scale + offsetY)
      const boxWidth = Math.abs(normalizedX2 - normalizedX1) * scale
      const boxHeight = Math.abs(normalizedY2 - normalizedY1) * scale

      return {
        class: DEFAULT_CLASS,
        x: boxX,
        y: boxY,
        width: boxWidth,
        height: boxHeight,
        confidence: Number(detection?.confidence ?? detection?.conf) || undefined,
        answer: '', expectedAnswer: '', answerType: 'choice'
      }
    })

    if (!active) return
    img.labels = mergeDetections((img.labels ?? []).map(toTemplateLabel), mappedLabels.map(toTemplateLabel)).map(toViewLabel)
    img.predictionsLoaded = true
  } catch (error: any) {
    console.error('Error fetching predictions:', error)
    if (active) img.predictionError = error instanceof Error ? error.message : '自動偵測失敗，請確認連線後重試'
  } finally {
    img.isPredicting = false
  }
}

const fetchPredictionsForCurrentImage = async () => {
  const img = currentImage.value
  if (!img) return

  await fetchPredictionsForImage(img)
  loadImage()
  // 學生卷 OCR 移到結果頁面執行，這裡只做 YOLO 偵測框框位置
}

const retryPrediction = async () => {
  const img = currentImage.value
  if (!img || locked.value) return
  if (img.labels?.length && !await askConfirm({ title: '重新偵測', message: '偵測會校正重疊的答案框並補上新框；既有題號與正解會保留，確定繼續嗎？', confirmText: '重新偵測' })) return
  if (!active || locked.value) return

  img.predictionsLoaded = false
  img.predictionError = undefined
  selectedLabelIndex.value = -1
  await fetchPredictionsForCurrentImage()
}

const endDrawing = () => {
  // 1. 結束平移
  if (isPanning.value) {
    stopPan()
    return
  }

  // 2. [新增] 結束框框拖曳
  if (draggingLabelIndex.value !== -1) {
    draggingLabelIndex.value = -1 // 重置拖曳狀態
    return
  }

  if (locked.value) { isDrawing.value = false; return }

  // 3. 結束畫新框 (原本的邏輯)
  if (!isDrawing.value || !currentImage.value) return

  isDrawing.value = false

  const width = currentX.value - startX.value
  const height = currentY.value - startY.value

  if (Math.abs(width) > 10 && Math.abs(height) > 10) {
    // ... (維持原本的新增 Label 邏輯) ...
    const label: Label = {
      class: currentClass.value,
      x: Math.min(startX.value, currentX.value),
      y: Math.min(startY.value, currentY.value),
      width: Math.abs(width),
      height: Math.abs(height),
      answer: '', expectedAnswer: '', answerType: 'choice'
    }

    if (currentMode.value === 'name' && draft.value) {
      draft.value.nameBox = { x: label.x, y: label.y, width: label.width, height: label.height }
      draft.value.nameBoxDirty = true
      loadImage()
      return
    }

    if (!currentImage.value.labels) {
      currentImage.value.labels = []
    }
    currentImage.value.labels.push(label)

    focusLabelInput(currentImage.value.labels.length - 1)
    selectedLabelIndex.value = currentImage.value.labels.length - 1 // 新增完自動選中
    loadImage()
  }
}
const removeLabel = (index: number) => {
  if (locked.value) return
  const img = currentImage.value
  if (img && img.labels) {
    img.labels.splice(index, 1)
    if (selectedLabelIndex.value === index) {
      selectedLabelIndex.value = -1
    } else if (selectedLabelIndex.value > index) {
      selectedLabelIndex.value--
    }
    loadImage()
  }
}

const clearLabels = async () => {
  if (locked.value) return
  const img = currentImage.value
  if (!img || !img.labels || img.labels.length === 0) return

  const confirmed = await askConfirm({
    title: '清除標註',
    message: `確定要清除「${img.name}」的全部 ${img.labels.length} 個標註嗎？`,
    confirmText: '清除',
    danger: true,
  })
  if (!confirmed || !active || locked.value) return

  img.labels = []
  selectedLabelIndex.value = -1
  loadImage()
}

const getCanvasCoords = (event: MouseEvent) => {
  if (!canvas.value) return { x: 0, y: 0 }

  const rect = canvas.value.getBoundingClientRect()
  // 畫布以 CSS 縮放顯示（設計版面為響應式），需換算回內部座標
  const scaleX = rect.width > 0 ? canvas.value.width / rect.width : 1
  const scaleY = rect.height > 0 ? canvas.value.height / rect.height : 1
  return {
    x: ((event.clientX - rect.left) * scaleX - panX.value) / zoom.value,
    y: ((event.clientY - rect.top) * scaleY - panY.value) / zoom.value
  }
}

const startPan = (event: MouseEvent) => {
  isPanning.value = true
  startX.value = event.clientX
  startY.value = event.clientY
}

const handlePanMove = (event: MouseEvent) => {
  if (!isPanning.value) return

  const dx = event.clientX - startX.value
  const dy = event.clientY - startY.value

  panX.value += dx
  panY.value += dy

  startX.value = event.clientX
  startY.value = event.clientY

  loadImage()
}

const stopPan = () => {
  isPanning.value = false
}

// 以指定的畫布座標為中心縮放（維持該點在畫面上的位置不動）
const zoomAt = (centerX: number, centerY: number, targetZoom: number) => {
  const oldZoom = zoom.value
  const newZoom = Math.min(3, Math.max(0.2, targetZoom))
  if (newZoom === oldZoom) return
  panX.value = centerX - ((centerX - panX.value) / oldZoom) * newZoom
  panY.value = centerY - ((centerY - panY.value) / oldZoom) * newZoom
  zoom.value = newZoom
  loadImage()
}

const handleWheel = (event: WheelEvent) => {
  if (!canvas.value) return
  // 滾輪縮放以游標位置為中心
  const rect = canvas.value.getBoundingClientRect()
  const scaleX = rect.width > 0 ? canvas.value.width / rect.width : 1
  const scaleY = rect.height > 0 ? canvas.value.height / rect.height : 1
  const centerX = (event.clientX - rect.left) * scaleX
  const centerY = (event.clientY - rect.top) * scaleY
  zoomAt(centerX, centerY, zoom.value + (event.deltaY < 0 ? 0.1 : -0.1))
}

const changeZoom = (delta: number) => {
  zoomAt(CANVAS_WIDTH / 2, CANVAS_HEIGHT / 2, zoom.value + delta)
}

const resetView = () => {
  panX.value = 0
  panY.value = 0
  zoom.value = 1
  loadImage()
}

const selectImage = (index: number) => {
  currentImageIndex.value = index
}

const previousImage = () => {
  if (currentImageIndex.value > 0) {
    currentImageIndex.value--
  }
}

// [新增] 排序標註：從右上到左下（先上到下，再右到左）
const sortLabelsRightToLeft = (labels: Label[]): Label[] => {
  return [...labels].sort((a, b) => {
    // 先按 Y 座標排序（小到大，從上到下）
    const yDiff = Math.abs(a.y - b.y)
    if (yDiff > 10) { // 如果 Y 座標差異大於 10px，認為是不同行
      return a.y - b.y
    }
    // 同一行內，按 X 座標排序（大到小，從右到左）
    return b.x - a.x
  })
}

// [新增] 直式考卷排序：左半部優先，每半部內由上到下、由左到右
const sortLabelsVertical = (labels: Label[]): Label[] => {
  if (labels.length === 0) return labels

  const centerXs = labels.map(l => l.x + l.width / 2).sort((a, b) => a - b)
  const midLine = centerXs[Math.floor(centerXs.length / 2)] ?? 0

  return [...labels].sort((a, b) => {
    const aIsLeft = (a.x + a.width / 2) < midLine
    const bIsLeft = (b.x + b.width / 2) < midLine

    // 左半部優先於右半部
    if (aIsLeft !== bIsLeft) return aIsLeft ? -1 : 1

    // 同一半部內：先按 Y（由上到下）
    const yDiff = Math.abs(a.y - b.y)
    if (yDiff > 10) return a.y - b.y

    // 同一行內：按 X（由左到右）
    return a.x - b.x
  })
}

// [新增] 自動排序：根據圖片寬高判斷直式/橫式並排序
const autoSort = async () => {
  if (locked.value) return
  const img = currentImage.value
  if (!img?.labels || img.labels.length === 0 || !img.preview) return

  const previewImg = await loadPreviewImage(img.preview)
  const isVertical = previewImg.height > previewImg.width
  if (!active || locked.value) return

  if (isVertical) {
    img.labels = sortLabelsVertical(img.labels)
    showToast('已偵測為直式考卷，排序完成（左半部優先，由上到下、由左到右）', 'success')
  } else {
    img.labels = sortLabelsRightToLeft(img.labels)
    showToast('已偵測為橫式考卷，排序完成（由上到下、由右到左）', 'success')
  }

  loadImage()
}

const nextImage = () => {
  if (currentImageIndex.value < displayedImages.value.length - 1) {
    currentImageIndex.value++
  }
}

const goToUpload = () => {
  router.push({ name: 'upload' })
}

const removeNameBox = () => {
  if (locked.value || !draft.value) return
  draft.value.nameBox = null
  draft.value.nameBoxDirty = true
  loadImage()
}

const reloadTemplate = async () => {
  if (!draft.value?.id || locked.value) return
  if (!await askConfirm({ title: '重新載入模板', message: '重新載入會捨棄尚未儲存的變更，確定繼續嗎？', confirmText: '重新載入', danger: true })) return
  await router.replace({ name: 'label', params: { id: draft.value.id } })
  router.go(0)
}

const saveCurrentTemplate = async () => {
  const value = draft.value
  if (!value || locked.value || invalidAnswers.value || invalidMetadata.value || !hasAnswers.value) return
  saving.value = true
  saveError.value = ''
  try {
    value.labels = (masterKeyImage.value?.labels ?? []).map(toTemplateLabel)
    await saveTemplate(value)
    if (!active) return
    showToast('模板已儲存', 'success')
    clearDraft()
    await router.push({ name: 'upload', query: { templates: '1' } })
  } catch (error) {
    if (active) saveError.value = error instanceof Error ? error.message : '儲存失敗，請稍後再試'
  } finally { saving.value = false }
}
</script>

<style scoped>
.label-container {
  max-width: 1376px;
  margin: 0 auto;
  padding: var(--space-6) var(--page-pad);
}

.no-images {
  max-width: 480px;
  margin: 48px auto;
  text-align: center;
  padding: 48px 32px;
}

.no-images p {
  font-size: var(--text-md);
  color: var(--text-2);
  margin: 0 0 20px;
}

.labeling-workspace {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}

@media (max-width: 1100px) {
  .labeling-workspace {
    grid-template-columns: 1fr;
  }
}

/* ── 側欄 ── */
.sidebar {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: calc(100vh - 110px);
  overflow-y: auto;
}

.view-toggle {
  width: 100%;
}

.image-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.image-list-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  background: transparent;
  border: 1px solid transparent;
  transition: background var(--duration-fast) var(--ease);
}

.image-list-item:hover {
  background: var(--surface-hover);
}

.image-list-item.active {
  background: var(--accent-subtle);
  border-color: var(--accent-border);
}

.thumb {
  width: 32px;
  height: 40px;
  object-fit: cover;
  background: #fff;
  border: 1px solid var(--border-default);
  border-radius: 3px;
  flex-shrink: 0;
}

.thumb--empty {
  display: inline-block;
  background: var(--surface-sunken);
}

.item-text {
  flex: 1;
  min-width: 0;
}

.item-name {
  display: block;
  font-size: var(--text-sm);
  font-family: var(--font-mono);
  color: var(--text-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.image-list-item.active .item-name {
  color: var(--accent-active);
}

.item-count {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-3);
}

/* ── 畫布卡片 ── */
.canvas-card {
  padding: 0;
  overflow: hidden;
}

.canvas-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-default);
  flex-wrap: wrap;
}

.toolbar-hint {
  font-size: var(--text-xs);
  color: var(--text-3);
}

.spacer {
  flex: 1;
}

.zoom-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-2);
  width: 44px;
  text-align: center;
}

.canvas-area {
  background: var(--surface-sunken);
  padding: 24px;
  display: flex;
  justify-content: center;
  overflow: hidden;
}

canvas {
  max-width: 100%;
  height: auto;
  background-color: white;
  box-shadow: var(--shadow-md);
  border-radius: 4px;
  transition: cursor 0.1s;
}

.canvas-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-top: 1px solid var(--border-default);
  flex-wrap: wrap;
}

.image-counter {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-2);
}

/* ── 右欄面板 ── */
.side-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-card {
  padding: 16px;
}

.panel-label {
  margin: 0 0 8px;
}

.class-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.hint-text {
  font-size: var(--text-xs);
  color: var(--text-3);
}

.batch-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

/* ── 標註清單 ── */
.label-scroll {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

.label-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  border: 1px solid var(--border-default);
  background: var(--surface-card);
  transition: border-color var(--duration-fast) var(--ease);
}

.label-item.selected {
  border-color: var(--border-focus);
  background: var(--accent-subtle);
}

.label-index {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--text-2);
  width: 24px;
  flex-shrink: 0;
}

.label-name {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--text-1);
}

.label-expected {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.input-prefix {
  font-size: var(--text-xs);
  color: var(--text-3);
}

.expected-value {
  width: 64px;
  text-align: center;
}

.no-labels {
  margin: 0;
  color: var(--text-3);
  font-size: var(--text-sm);
}

/* ── 底部操作卡 ── */
.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  user-select: none;
  color: var(--text-1);
  font-size: var(--text-sm);
  margin-bottom: 14px;
}

.checkbox-label input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
  accent-color: var(--accent);
  flex-shrink: 0;
}

.panel-actions {
  display: flex;
  gap: 8px;
}

.panel-actions .ds-btn {
  flex: 1;
}

.results-btn {
  width: 100%;
  margin-top: 8px;
}
.template-fields { display: grid; gap: 8px; margin-bottom: 14px; }
.label-item { flex-wrap: wrap; }
.label-type { display: flex; align-items: center; gap: 8px; width: 100%; }
.label-type select { flex: 1; }
.label-item.invalid, .label-item.invalid .expected-value { border-color: var(--danger); }
.label-item.invalid .expected-value { background: var(--danger-bg); }
.field-error { color: var(--danger); margin: 4px 0; }
.template-fields select { width: 100%; }
.batch-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.batch-bar select { flex: 1; }
.batch-all { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.batch-hint { margin: 0 0 10px; }
.label-check { margin: 0; accent-color: var(--accent); }
</style>
