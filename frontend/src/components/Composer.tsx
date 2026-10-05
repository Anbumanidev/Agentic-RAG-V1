import { useRef, useState, type KeyboardEvent } from 'react'
import { Globe, Loader2, Paperclip, SendHorizonal } from 'lucide-react'

interface Props {
  disabled: boolean
  uploading: boolean
  accept: string
  onSend: (text: string, forceWeb: boolean) => void
  onFiles: (files: File[]) => void
}

export function Composer({ disabled, uploading, accept, onSend, onFiles }: Props) {
  const [text, setText] = useState('')
  const [forceWeb, setForceWeb] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const submit = () => {
    const value = text.trim()
    if (!value || disabled) return
    onSend(value, forceWeb)
    setText('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="border-t border-slate-800 bg-slate-950 px-4 py-3">
      <div className="mx-auto max-w-3xl rounded-2xl border border-slate-700 bg-slate-900 focus-within:border-indigo-500">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask anything, paste a URL to load it, or attach a file…"
          className="block w-full resize-none bg-transparent px-4 pt-3 text-sm outline-none placeholder:text-slate-500"
        />
        <div className="flex items-center justify-between px-2 pb-2">
          <div className="flex items-center gap-1">
            <input
              ref={fileRef}
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
            <button
              title="Attach files"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50"
            >
              {uploading ? <Loader2 size={18} className="animate-spin" /> : <Paperclip size={18} />}
            </button>
            <button
              title="Always search the web for this message"
              onClick={() => setForceWeb((v) => !v)}
              className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs ${
                forceWeb ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:bg-slate-800'
              }`}
            >
              <Globe size={14} /> Web search
            </button>
          </div>
          <button
            onClick={submit}
            disabled={disabled || !text.trim()}
            className="rounded-lg bg-indigo-600 p-2 hover:bg-indigo-500 disabled:opacity-40"
          >
            <SendHorizonal size={18} />
          </button>
        </div>
      </div>
      <p className="mx-auto mt-1.5 max-w-3xl text-center text-[11px] text-slate-500">
        Answers come from your URLs &amp; files first, then the top 10 web pages. Open-source models may make mistakes.
      </p>
    </div>
  )
}
