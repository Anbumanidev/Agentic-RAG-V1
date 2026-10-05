import { MessageSquarePlus, MessagesSquare, Trash2 } from 'lucide-react'
import type { Health, Session } from '../types'

interface Props {
  sessions: Session[]
  activeId: string | null
  health: Health | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
}

export function Sidebar({ sessions, activeId, health, onSelect, onNew, onDelete }: Props) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-slate-800 bg-slate-900/60">
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500 text-lg">
          🧠
        </div>
        <div>
          <div className="text-sm font-semibold">Agentic RAG</div>
          <div className="text-xs text-slate-400">Multi-agent · open source</div>
        </div>
      </div>
      <div className="px-3">
        <button
          onClick={onNew}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium hover:bg-indigo-500"
        >
          <MessageSquarePlus size={16} /> New chat
        </button>
      </div>
      <nav className="scrollbar-thin mt-4 flex-1 space-y-1 overflow-y-auto px-2">
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`group flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm ${
              s.id === activeId ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-800/60'
            }`}
          >
            <MessagesSquare size={14} className="shrink-0 text-slate-500" />
            <span className="flex-1 truncate">{s.title}</span>
            <button
              title="Delete chat"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(s.id)
              }}
              className="hidden text-slate-500 hover:text-red-400 group-hover:block"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
        {sessions.length === 0 && (
          <p className="px-3 text-xs text-slate-500">No conversations yet.</p>
        )}
      </nav>
      <div className="border-t border-slate-800 px-4 py-3 text-xs text-slate-400">
        {health ? (
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full ${health.llm_reachable ? 'bg-emerald-400' : 'bg-red-500'}`}
              />
              <span className="truncate">
                {health.llm_provider} · {health.llm_model}
              </span>
            </div>
            <div className="truncate">Search: {health.web_search}</div>
          </div>
        ) : (
          <span>Connecting to backend…</span>
        )}
      </div>
    </aside>
  )
}
