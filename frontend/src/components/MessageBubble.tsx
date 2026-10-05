import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  BookOpen,
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  FileText,
  Globe,
  Link2,
  Loader2,
  User,
} from 'lucide-react'
import type { Attachment, Message, Route, Source } from '../types'

const ROUTE_BADGE: Record<string, { label: string; className: string; icon: typeof Globe }> = {
  knowledge: { label: 'Knowledge base', className: 'bg-emerald-500/15 text-emerald-300', icon: BookOpen },
  web: { label: 'Web research', className: 'bg-sky-500/15 text-sky-300', icon: Globe },
  conversation: { label: 'Memory', className: 'bg-violet-500/15 text-violet-300', icon: Brain },
  ingest_only: { label: 'Content loaded', className: 'bg-amber-500/15 text-amber-300', icon: Link2 },
  documents: { label: 'Documents', className: 'bg-teal-500/15 text-teal-300', icon: FileText },
}

function RouteBadge({ route }: { route?: Route }) {
  if (!route || !ROUTE_BADGE[route]) return null
  const { label, className, icon: Icon } = ROUTE_BADGE[route]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${className}`}>
      <Icon size={12} /> {label}
    </span>
  )
}

function SourceList({ sources }: { sources: Source[] }) {
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? sources : sources.filter((s) => s.used !== false).slice(0, 6)
  const hidden = sources.length - visible.length
  return (
    <div className="mt-3 space-y-1">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">Sources</div>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {visible.map((s) => {
          const Icon = s.kind === 'file' ? FileText : s.kind === 'web' ? Globe : Link2
          const body = (
            <>
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-slate-700 text-[10px] font-semibold">
                {s.index}
              </span>
              <Icon size={12} className="shrink-0 text-slate-400" />
              <span className="truncate">{s.title}</span>
              {s.fetched === false && <span className="text-[10px] text-slate-500">(snippet)</span>}
            </>
          )
          return s.url ? (
            <a
              key={s.index}
              href={s.url}
              target="_blank"
              rel="noreferrer"
              title={s.url}
              className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-300 hover:border-slate-600"
            >
              {body}
            </a>
          ) : (
            <div
              key={s.index}
              className="flex items-center gap-2 rounded-md border border-slate-800 bg-slate-900 px-2 py-1.5 text-xs text-slate-300"
            >
              {body}
            </div>
          )
        })}
      </div>
      {hidden > 0 && (
        <button onClick={() => setShowAll(true)} className="text-xs text-indigo-300 hover:underline">
          Show all {sources.length} pages read
        </button>
      )}
    </div>
  )
}

function AttachmentList({ attachments, pending }: { attachments: Attachment[]; pending?: boolean }) {
  return (
    <div className="flex max-w-[80%] flex-wrap justify-end gap-2">
      {attachments.map((a) => {
        const Icon = a.kind === 'url' ? Link2 : FileText
        return (
          <div
            key={a.id}
            title={a.source}
            className="flex max-w-xs items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 text-sm"
          >
            {pending ? (
              <Loader2 size={16} className="shrink-0 animate-spin text-indigo-300" />
            ) : (
              <Icon size={16} className="shrink-0 text-indigo-300" />
            )}
            <div className="min-w-0">
              <div className="truncate">{a.title}</div>
              <div className="text-[11px] text-slate-400">
                {pending ? 'Loading…' : `${a.kind === 'url' ? 'URL' : 'File'}${a.chunks ? ` · ${a.chunks} chunks` : ''}`}
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function MessageBubble({ message }: { message: Message }) {
  const [open, setOpen] = useState(false)
  const isUser = message.role === 'user'
  const steps = message.meta?.steps ?? []
  const sources = message.meta?.sources ?? []

  const attachments = message.meta?.attachments ?? []
  if (isUser && attachments.length > 0) {
    return (
      <div className="flex justify-end gap-3">
        <AttachmentList attachments={attachments} pending={message.pending} />
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700">
          <User size={16} />
        </div>
      </div>
    )
  }

  if (isUser) {
    return (
      <div className="flex justify-end gap-3">
        <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2.5 text-sm">
          {message.content}
        </div>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-700">
          <User size={16} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-500/20 text-indigo-300">
        <Bot size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <RouteBadge route={message.meta?.route} />
          {steps.length > 0 && (
            <button
              onClick={() => setOpen((v) => !v)}
              className="inline-flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
            >
              {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Agent trace ({steps.length} steps)
            </button>
          )}
        </div>

        {(open || (message.pending && !message.content)) && steps.length > 0 && (
          <ol className="mb-2 space-y-1 border-l border-slate-700 pl-3">
            {steps.map((s, i) => (
              <li key={i} className="text-xs">
                <span className={`font-medium ${s.status === 'error' ? 'text-red-400' : 'text-indigo-300'}`}>
                  {s.agent}
                </span>
                <span className="text-slate-400"> — {s.detail}</span>
              </li>
            ))}
          </ol>
        )}

        {message.pending && !message.content && (
          <div className="flex items-center gap-2 text-sm text-slate-400">
            <Loader2 size={14} className="animate-spin" />
            {steps.length ? steps[steps.length - 1].agent + ' working…' : 'Thinking…'}
          </div>
        )}

        {message.content && (
          <div className="prose prose-invert prose-sm max-w-none break-words prose-pre:bg-slate-900 prose-a:text-indigo-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
        )}
        {message.error && <div className="mt-2 text-xs text-red-400">{message.error}</div>}
        {!message.pending && sources.length > 0 && <SourceList sources={sources} />}
      </div>
    </div>
  )
}
