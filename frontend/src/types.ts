export type Route = 'ingest_only' | 'conversation' | 'knowledge' | 'web' | null

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface KnowledgeDocument {
  id: string
  session_id: string
  kind: 'url' | 'file'
  source: string
  title: string
  chunks: number
  chars: number
  created_at: string
}

export interface Source {
  index: number
  title: string
  url?: string | null
  kind: 'url' | 'file' | 'web'
  snippet?: string
  fetched?: boolean
  used?: boolean
  score?: number
}

export interface Step {
  agent: string
  detail: string
  status?: string
  route?: Route
}

export interface MessageMeta {
  route?: Route
  sources?: Source[]
  steps?: Step[]
  ingested?: Pick<KnowledgeDocument, 'id' | 'title' | 'source' | 'kind' | 'chunks'>[]
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  meta: MessageMeta
  pending?: boolean
  error?: string
}

export interface SessionDetail extends Session {
  messages: Message[]
  documents: KnowledgeDocument[]
}

export interface Health {
  status: string
  llm_provider: string
  llm_model: string
  llm_reachable: boolean
  embedding_model: string
  web_search: string
  supported_files: string[]
}

export type StreamEvent =
  | ({ type: 'step' } & Step)
  | { type: 'token'; content: string }
  | { type: 'documents_changed' }
  | { type: 'error'; message: string }
  | ({ type: 'done'; message_id: string; answer: string } & MessageMeta)
