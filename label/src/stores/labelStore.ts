let labelCache: any[] | null = null

export const setLabelData = (data: any[]) => {
  labelCache = data
}

export const getLabelData = () => labelCache

export const clearLabelData = () => {
  labelCache = null
}