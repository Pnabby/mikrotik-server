const API_URL = String(import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

export async function getSupportSettings() {
  const response = await fetch(`${API_URL}/api/support`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) throw new Error('Support settings could not be loaded.')
  return response.json()
}
