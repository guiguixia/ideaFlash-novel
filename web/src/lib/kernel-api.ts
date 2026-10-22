import { authHeaders, getAuthToken, setAuthToken } from './auth-session'

type KernelEnvelope<T> = {
  code?: number
  msg?: string
  message?: string
  data?: T
  list?: T
}

async function kernelRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const response = await fetch(path, {
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
