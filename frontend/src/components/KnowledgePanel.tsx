import { useState, type FormEvent } from 'react'
import { FileText, Link2, Loader2, Plus, Trash2, Upload } from 'lucide-react'
import type { KnowledgeDocument } from '../types'

interface Props {
  documents: KnowledgeDocument[]
  busy: boolean
  accept: string
  onAddUrl: (url: string) => Promise<void>
  onFiles: (files: File[]) => void
  onDelete: (id: string) => void
}

export function KnowledgePanel({ documents, busy, accept, onAddUrl, onFiles, onDelete }: Props) {
  const [url, setUrl] = useState('')
  const [dragging, setDragging] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim()) return
    await onAddUrl(url.trim())
    setUrl('')
  }

  return (
    <aside className="hidden w-80 shrink-0 flex-col border-l border-slate-800 bg-slate-900/40 lg:flex">
      <div className="border-b border-slate-800 px-4 py-4">
        <h2 className="text-sm font-semibold">Knowledge base</h2>
        <p className="text-xs text-slate-400">URLs and files loaded into this chat</p>
      </div>
      <div className="space-y-3 p-4">
        <form onSubmit={submit} className="flex gap-2">
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/article"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs outline-none focus:border-indigo-500"
          />
          <button
            type="submit"
            disabled={busy || !url.trim()}
            title="Load URL"
            className="rounded-lg bg-slate-700 px-2.5 hover:bg-slate-600 disabled:opacity-40"
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          </button>
        </form>
        <label
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragging(false)
            const files = Array.from(e.dataTransfer.files)
            if (files.length) onFiles(files)
          }}
          className={`flex cursor-pointer flex-col items-center gap-1 rounded-lg border border-dashed px-3 py-4 text-center text-xs ${
            dragging ? 'border-indigo-400 bg-indigo-500/10' : 'border-slate-700 text-slate-400 hover:border-slate-500'
          }`}
        >
          <Upload size={16} />
          Drop files or click to upload
          <span className="text-[10px] text-slate-500">PDF, DOCX, TXT, MD, CSV, JSON, HTML, code</span>
          <input
            type="file"
            multiple
            accept={accept}
            className="hidden"
            onChange={(e) => {
              const files = Array.from(e.target.files ?? [])
              if (files.length) onFiles(files)
              e.target.value = ''
            }}
          />
        </label>
      </div>
      <ul className="scrollbar-thin flex-1 space-y-2 overflow-y-auto px-4 pb-4">
        {documents.map((d) => (
          <li
            key={d.id}
            className="group flex items-start gap-2 rounded-lg border border-slate-800 bg-slate-900 p-2.5 text-xs"
          >
            {d.kind === 'url' ? (
              <Link2 size={14} className="mt-0.5 shrink-0 text-amber-300" />
            ) : (
              <FileText size={14} className="mt-0.5 shrink-0 text-emerald-300" />
            )}
            <div className="min-w-0 flex-1">
              <div className="truncate font-medium" title={d.title}>
                {d.title}
              </div>
              {d.kind === 'url' ? (
                <a href={d.source} target="_blank" rel="noreferrer" className="block truncate text-slate-500 hover:underline">
                  {d.source}
                </a>
              ) : null}
              <div className="text-slate-500">
                {d.chunks} chunks · {(d.chars / 1000).toFixed(1)}k chars
              </div>
            </div>
            <button
              title="Remove"
              onClick={() => onDelete(d.id)}
              className="text-slate-500 opacity-0 hover:text-red-400 group-hover:opacity-100"
            >
              <Trash2 size={14} />
            </button>
          </li>
        ))}
        {documents.length === 0 && (
          <li className="text-center text-xs text-slate-500">
            Nothing loaded yet. Paste a URL in the chat or attach a file.
          </li>
        )}
      </ul>
    </aside>
  )
}
