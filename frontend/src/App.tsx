import { useCallback, useEffect, useRef, useState } from 'react'
import { BookOpen, Brain, Globe, X } from 'lucide-react'
import { api } from './api'
import { Composer } from './components/Composer'
import { KnowledgePanel } from './components/KnowledgePanel'
import { MessageBubble } from './components/MessageBubble'
import { Sidebar } from './components/Sidebar'
import type { Attachment, Health, KnowledgeDocument, Message, Session, StreamEvent } from './types'

const DEFAULT_ACCEPT = '.pdf,.docx,.txt,.md,.csv,.json,.html,.htm'

const SUGGESTIONS = [
  { icon: Globe, text: 'https://en.wikipedia.org/wiki/Retrieval-augmented_generation' },
  { icon: BookOpen, text: 'Summarize the document I just uploaded' },
  { icon: Brain, text: 'What are the latest developments in open-source LLMs?' },
]

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([])
  const [streaming, setStreaming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const activeIdRef = useRef<string | null>(null)

  const accept = health?.supported_files.join(',') ?? DEFAULT_ACCEPT

  const notify = (msg: string) => {
    setToast(msg)
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 6000)
  }

  const refreshSessions = useCallback(async () => setSessions(await api.listSessions()), [])

  const loadSession = useCallback(async (id: string) => {
    activeIdRef.current = id
    const detail = await api.getSession(id)
    if (activeIdRef.current !== id) return
    setActiveId(id)
    setMessages(detail.messages)
    setDocuments(detail.documents)
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api
      .listSessions()
      .then((list) => {
        setSessions(list)
        if (list.length) loadSession(list[0].id)
      })
      .catch((e) => notify(`Backend unreachable: ${e.message}`))
  }, [loadSession])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const ensureSession = async (): Promise<string> => {
    if (activeId) return activeId
    const session = await api.createSession()
    activeIdRef.current = session.id
    setActiveId(session.id)
    setMessages([])
    setDocuments([])
    await refreshSessions()
    return session.id
  }

  const newChat = async () => {
    const session = await api.createSession()
    await refreshSessions()
    await loadSession(session.id)
  }

  const deleteChat = async (id: string) => {
    await api.deleteSession(id)
    const list = await api.listSessions()
    setSessions(list)
    if (id === activeId) {
      if (list.length) await loadSession(list[0].id)
      else {
        activeIdRef.current = null
        setActiveId(null)
        setMessages([])
        setDocuments([])
      }
    }
  }

  const refreshDocuments = async (id: string) => {
    const docs = await api.listDocuments(id)
    if (activeIdRef.current === id) setDocuments(docs)
  }

  const send = async (text: string, forceWeb: boolean) => {
    if (streaming) return
    const sid = await ensureSession()
    const userMsg: Message = { id: crypto.randomUUID(), role: 'user', content: text, meta: {} }
    const botId = crypto.randomUUID()
    const botMsg: Message = { id: botId, role: 'assistant', content: '', meta: { steps: [] }, pending: true }
    setMessages((m) => [...m, userMsg, botMsg])
    setStreaming(true)

    const update = (fn: (m: Message) => Message) =>
      setMessages((list) => list.map((m) => (m.id === botId ? fn(m) : m)))

    try {
      await api.chat(sid, text, forceWeb, (event: StreamEvent) => {
        switch (event.type) {
          case 'step': {
            const { type: _t, ...step } = event
            void _t
            update((m) => ({
              ...m,
              meta: { ...m.meta, steps: [...(m.meta.steps ?? []), step], route: step.route ?? m.meta.route },
            }))
            break
          }
          case 'token':
            update((m) => ({ ...m, content: m.content + event.content }))
            break
          case 'documents_changed':
            refreshDocuments(sid)
            break
          case 'error':
            update((m) => ({ ...m, error: event.message }))
            break
          case 'done':
            update((m) => ({
              ...m,
              content: event.answer || m.content,
              pending: false,
              meta: { route: event.route, sources: event.sources, steps: event.steps, ingested: event.ingested },
            }))
            break
        }
      })
    } catch (e) {
      update((m) => ({ ...m, pending: false, error: (e as Error).message }))
    } finally {
      update((m) => ({ ...m, pending: false }))
      setStreaming(false)
      refreshSessions()
    }
  }

  const showAttachment = async (sid: string, attachments: Attachment[], load: () => Promise<Message | null>) => {
    const tempId = crypto.randomUUID()
    const pendingMsg: Message = {
      id: tempId,
      role: 'user',
      content: '',
      meta: { attachments },
      pending: true,
    }
    if (activeIdRef.current === sid) setMessages((m) => [...m, pendingMsg])
    try {
      const saved = await load()
      setMessages((list) => list.flatMap((m) => (m.id === tempId ? (saved ? [saved] : []) : [m])))
    } catch (e) {
      setMessages((list) => list.filter((m) => m.id !== tempId))
      throw e
    }
  }

  const uploadFiles = async (files: File[]) => {
    setBusy(true)
    try {
      const sid = await ensureSession()
      const placeholders = files.map((f) => ({ id: f.name, title: f.name, source: f.name, kind: 'file' as const }))
      let errors: string[] = []
      await showAttachment(sid, placeholders, async () => {
        const res = await api.uploadFiles(sid, files)
        errors = res.errors
        return res.message
      })
      await refreshDocuments(sid)
      refreshSessions()
      if (errors.length) notify(`Some files failed: ${errors.join('; ')}`)
    } catch (e) {
      notify(`Upload failed: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const addUrl = async (url: string) => {
    setBusy(true)
    try {
      const sid = await ensureSession()
      await showAttachment(sid, [{ id: url, title: url, source: url, kind: 'url' }], async () => {
        const doc = await api.addUrl(sid, url)
        return doc.message
      })
      await refreshDocuments(sid)
      refreshSessions()
    } catch (e) {
      notify(`Could not load URL: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const deleteDocument = async (docId: string) => {
    if (!activeId) return
    await api.deleteDocument(activeId, docId)
    await refreshDocuments(activeId)
  }

  return (
    <div className="flex h-full">
      <Sidebar
        sessions={sessions}
        activeId={activeId}
        health={health}
        onSelect={loadSession}
        onNew={newChat}
        onDelete={deleteChat}
      />
      <main className="flex min-w-0 flex-1 flex-col">
        <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-y-auto">
          {messages.length === 0 ? (
            <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-6 text-center">
              <div className="mb-4 text-5xl">🧠</div>
              <h1 className="text-2xl font-semibold">What would you like to know?</h1>
              <p className="mt-2 text-sm text-slate-400">
                Paste a URL or attach a file and ask questions about it. Anything else is researched across the
                top 10 web pages. The conversation is remembered.
              </p>
              <div className="mt-6 grid w-full gap-2">
                {SUGGESTIONS.map(({ icon: Icon, text }) => (
                  <button
                    key={text}
                    onClick={() => send(text, false)}
                    className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900 px-4 py-3 text-left text-sm text-slate-300 hover:border-slate-600"
                  >
                    <Icon size={16} className="shrink-0 text-indigo-300" />
                    <span className="truncate">{text}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 px-4 py-6">
              {messages.map((m) => (
                <MessageBubble key={m.id} message={m} />
              ))}
            </div>
          )}
        </div>
        <Composer disabled={streaming} uploading={busy} accept={accept} onSend={send} onFiles={uploadFiles} />
      </main>
      <KnowledgePanel
        documents={documents}
        busy={busy}
        accept={accept}
        onAddUrl={addUrl}
        onFiles={uploadFiles}
        onDelete={deleteDocument}
      />
      {toast && (
        <div className="fixed bottom-24 left-1/2 z-50 flex max-w-lg -translate-x-1/2 items-center gap-3 rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm shadow-xl">
          <span>{toast}</span>
          <button onClick={() => setToast(null)} className="text-slate-400 hover:text-white">
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  )
}
