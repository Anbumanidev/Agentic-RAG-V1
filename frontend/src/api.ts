import type { Health, KnowledgeDocument, Message, Session, SessionDetail, StreamEvent } from './types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* ignore */
    }
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

const json = (body: unknown): RequestInit => ({
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<Health>('/api/health'),
  listSessions: () => request<Session[]>('/api/sessions'),
  createSession: () => request<Session>('/api/sessions', { method: 'POST' }),
  getSession: (id: string) => request<SessionDetail>(`/api/sessions/${id}`),
  deleteSession: (id: string) => request<void>(`/api/sessions/${id}`, { method: 'DELETE' }),
  listDocuments: (id: string) => request<KnowledgeDocument[]>(`/api/sessions/${id}/documents`),
  addUrl: (id: string, url: string) =>
    request<KnowledgeDocument & { message: Message }>(`/api/sessions/${id}/urls`, { method: 'POST', ...json({ url }) }),
  uploadFiles: (id: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<{ documents: KnowledgeDocument[]; errors: string[]; message: Message | null }>(
      `/api/sessions/${id}/files`,
      { method: 'POST', body: form },
    )
  },
  deleteDocument: (id: string, docId: string) =>
    request<void>(`/api/sessions/${id}/documents/${docId}`, { method: 'DELETE' }),

  async chat(
    id: string,
    message: string,
    forceWeb: boolean,
    onEvent: (e: StreamEvent) => void,
    signal?: AbortSignal,
  ) {
    const res = await fetch(`${BASE}/api/sessions/${id}/chat`, {
      method: 'POST',
      signal,
      ...json({ message, force_web: forceWeb }),
    })
    if (!res.ok || !res.body) throw new Error(`Chat failed (${res.status})`)
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finished = false
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) >= 0) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const line = raw.split('\n').find((l) => l.startsWith('data: '))
        if (!line) continue
        const event = JSON.parse(line.slice(6)) as StreamEvent
        if (event.type === 'done') finished = true
        onEvent(event)
      }
    }
    if (!finished) throw new Error('Connection closed before the answer finished')
  },
}
