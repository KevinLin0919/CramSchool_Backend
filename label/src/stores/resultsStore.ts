import { reactive } from 'vue'

// 統一的資料 store，跨頁面保存
interface ImageData {
  name: string
  preview: string
  labels?: any[]
  predictionsLoaded?: boolean
  isPredicting?: boolean
  predictionError?: string
  role: 'student' | 'master'
  // 答案卷來自已儲存模板時的模板 id，用來判斷該新增還是更新模板
  templateId?: number | null
  [key: string]: any
}

interface AppStore {
  studentImages: ImageData[]
  masterKeyImage: ImageData | null
  initialized: boolean // 標記是否已從 UploadView 初始化
}

const store = reactive<AppStore>({
  studentImages: [],
  masterKeyImage: null,
  initialized: false
})

// 從 UploadView 初始化（會清除舊資料）
export const initializeFromUpload = (students: ImageData[], master: ImageData | null) => {
  store.studentImages = students
  store.masterKeyImage = master
  store.initialized = true
}

// 更新學生圖片（保留現有資料結構）
export const updateStudentImages = (students: ImageData[]) => {
  store.studentImages = students
  if (students.length > 0) store.initialized = true
}

// 更新答案卷
export const updateMasterImage = (master: ImageData | null) => {
  store.masterKeyImage = master
  if (master) store.initialized = true
}

// 新增學生圖片（不影響現有圖片）
export const addStudentImages = (newStudents: ImageData[]) => {
  store.studentImages.push(...newStudents)
}

// 取得所有資料
export const getStoreData = () => ({
  studentImages: store.studentImages,
  masterKeyImage: store.masterKeyImage,
  initialized: store.initialized
})

// 檢查是否有資料
export const hasData = () => store.initialized && (store.studentImages.length > 0 || store.masterKeyImage !== null)

// 完全清除資料（重新開始）
export const clearAllData = () => {
  store.studentImages = []
  store.masterKeyImage = null
  store.initialized = false
}

// === 舊的 API（保持向後相容）===
export const setResultsData = (data: Record<string, any> | any[]) => {
  // 從 LabelView 進入 ResultsView 時調用
  if (data && typeof data === 'object' && 'students' in data) {
    store.studentImages = (data as any).students || []
    store.masterKeyImage = (data as any).masterKey || null
    store.initialized = true
  }
}

export const getResultsData = () => ({
  students: store.studentImages,
  masterKey: store.masterKeyImage
})

