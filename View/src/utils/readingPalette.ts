export const readingPapers = [
  { value: 'warm', label: '暖灰', color: '#bba673' },
  { value: 'white', label: '白色', color: '#ffffff' },
  { value: 'green', label: '淡绿', color: '#689b76' },
  { value: 'blue', label: '雾蓝', color: '#688eaf' },
  { value: 'rose', label: '浅玫瑰', color: '#b67587' },
  { value: 'lavender', label: '淡紫', color: '#8e7fae' },
  { value: 'sepia', label: '旧纸', color: '#a77b42' },
  { value: 'dark', label: '深灰', color: '#121816' },
  { value: 'custom', label: '自选颜色', color: '#bba673' },
]

export function readingPalette(paper: string, depth: number, custom: string) {
  const base = paper === 'custom' && /^#[a-f\d]{6}$/i.test(custom) ? custom : readingPapers.find(item => item.value === paper)?.color ?? '#bba673'
  const ratio = Math.max(0, Math.min(100, depth)) / 100
  const rgb = [1, 3, 5].map(at => Math.round(255 * (1 - ratio) + parseInt(base.slice(at, at + 2), 16) * ratio))
  const linear = rgb.map(value => { const c = value / 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4 })
  const luminance = linear[0]! * 0.2126 + linear[1]! * 0.7152 + linear[2]! * 0.0722
  const light = luminance > 0.179
  return {
    '--trial-bg': `rgb(${rgb.join(', ')})`,
    '--trial-ink': light ? '#000000' : '#ffffff',
    '--trial-muted': light ? '#000000' : '#ffffff',
    '--trial-line': light ? '#00000040' : '#ffffff55',
  }
}
