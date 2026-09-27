export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('無法讀取圖片，請換一張再試'))
    image.src = src
  })
}

export function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('無法讀取圖片'))
    reader.readAsDataURL(blob)
  })
}

// Browser image decoding applies EXIF orientation; all later uses share this JPEG.
export async function normalizeImage(file: File) {
  const source = URL.createObjectURL(file)
  try {
    const image = await loadImage(source)
    const scale = Math.min(1, 2400 / Math.max(image.naturalWidth, image.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('瀏覽器無法處理圖片')
    ctx.fillStyle = '#fff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((value) => value ? resolve(value) : reject(new Error('圖片轉換失敗')), 'image/jpeg', 0.9)
    })
    return { blob, preview: URL.createObjectURL(blob), width: canvas.width, height: canvas.height }
  } finally { URL.revokeObjectURL(source) }
}
