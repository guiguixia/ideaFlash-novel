import { authHeaders, getAuthToken, setAuthToken } from './auth-session'

type KernelEnvelope<T> = {
  code?: number
  msg?: string
  message?: string
  data?: T
  list?: T
}

const desktopApiBase = window.location.protocol === 'file:' ? 'http://127.0.0.1:8004' : ''
const apiUrl = (path: string): string => desktopApiBase ? new URL(path, desktopApiBase).toString() : path

async function kernelRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...authHeaders(init?.headers),
    },
  })
  const raw = await response.text()
  let json: KernelEnvelope<T> & { detail?: string | { msg?: string } } = {}
  if (raw.trim()) {
    try {
      json = JSON.parse(raw) as KernelEnvelope<T> & { detail?: string | { msg?: string } }
    } catch {
      throw new Error(`服务返回了无效响应（HTTP ${response.status}）`)
    }
  }
  if (!response.ok || (json.code != null && json.code !== 0)) {
    if (response.status === 401) setAuthToken(null)
    const detail = typeof json.detail === 'string' ? json.detail : json.detail?.msg
    throw new Error(json.msg || json.message || detail || (raw.trim() ? raw.slice(0, 200) : `请求失败（HTTP ${response.status}）`))
  }
  if (!raw.trim()) throw new Error(`服务返回空响应（HTTP ${response.status}）`)
  return (json.data ?? json.list ?? json) as T
}

function storeLoginToken(data: { access_token?: string; token?: string }): void {
  const token = data.access_token || data.token
  if (!token) throw new Error('Novel 未返回登录令牌')
  setAuthToken(token)
}

export async function loginLocal(username: string, password: string): Promise<void> {
  const data = await kernelRequest<{ access_token?: string; token?: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  storeLoginToken(data)
}

export function isLoggedIn(): boolean {
  return Boolean(getAuthToken())
}

export function logout(): void {
  setAuthToken(null)
}

export function kernelGet<T>(path: string): Promise<T> {
  return kernelRequest<T>(path)
}

export function kernelPost<T>(path: string, body?: unknown): Promise<T> {
  return kernelRequest<T>(path, { method: 'POST', body: body == null ? undefined : JSON.stringify(body) })
}

export function kernelPatch<T>(path: string, body?: unknown): Promise<T> {
  return kernelRequest<T>(path, { method: 'PATCH', body: JSON.stringify(body ?? {}) })
}

export function kernelDelete<T>(path: string): Promise<T> {
  return kernelRequest<T>(path, { method: 'DELETE' })
}

export function kernelUpload<T>(path: string, form: FormData): Promise<T> {
  return kernelRequest<T>(path, { method: 'POST', body: form })
}

export async function kernelStreamPost<T>(path: string, body: unknown, onChunk: (content: string) => void): Promise<T> {
  const response = await fetch(apiUrl(path), { method: 'POST', body: JSON.stringify(body), headers: authHeaders({ 'Content-Type': 'application/json', Accept: 'text/event-stream' }) })
  if (!response.ok || !response.body) throw new Error(`请求失败（HTTP ${response.status}）`)
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', done: T | null = null
  while (true) {
    const { value, done: finished } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !finished })
    const events = buffer.split('\n\n'); buffer = events.pop() || ''
    for (const raw of events) {
      const event = raw.match(/^event:\s*(.+)$/m)?.[1] || 'message', data = raw.match(/^data:\s*(.+)$/m)?.[1]
      if (!data) continue
      const payload = JSON.parse(data) as { content?: string; message?: string; session?: T }
      if (event === 'chunk' && payload.content) onChunk(payload.content)
      if (event === 'error') throw new Error(payload.message || '流式生成失败')
      if (event === 'done') done = (payload.session || payload) as T
    }
    if (finished) break
  }
  if (!done) throw new Error('流式生成未返回完成结果')
  return done
}
