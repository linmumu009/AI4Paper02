export type DigestContextLabel = '今日论文' | '最新一期' | '历史日报'

export function toLocalDateKey(value = new Date()): string {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function getDigestContextLabel(
  selectedDate: string,
  latestDate: string,
  today = toLocalDateKey(),
): DigestContextLabel {
  if (selectedDate && selectedDate === today) return '今日论文'
  if (selectedDate && selectedDate === latestDate) return '最新一期'
  return '历史日报'
}
