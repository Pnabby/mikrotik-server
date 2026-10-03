export function readPreference(key, fallback) {
  try { return window.localStorage.getItem(key) ?? fallback } catch { return fallback }
}

export function savePreference(key, value) {
  try { window.localStorage.setItem(key, value) } catch { /* Private browsing may disable storage. */ }
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme
}

export function initialTheme() {
  const saved = readPreference('vlad-wifi-theme', '')
  return ['light', 'dark'].includes(saved) ? saved : window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}
