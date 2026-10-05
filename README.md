# Agentic RAG V1

A fully open-source, **multi-agent RAG** system with a FastAPI + LangGraph backend and a React chat UI.

- **Chat with any URL** — paste a link in the chat (or add it in the Knowledge panel); it is scraped, chunked and indexed, and follow-up questions are answered from it with citations.
- **Chat with your files** — attach PDF, DOCX, TXT, MD, CSV, JSON, HTML or source files; later questions are answered from them.
- **Web research for everything else** — if the question is outside your URLs/files, the agents search the web, read the **top 10 pages** and synthesize a cited answer.
- **Conversation memory** — every chat is persisted (SQLite). Recent turns are sent to the model and older turns are compressed into a running summary, so follow-ups like "what about the second point?" or "what's my name?" work end-to-end.

Everything runs locally with open-source components: [Ollama](https://ollama.com) (or any OpenAI-compatible server such as vLLM / llama.cpp / LM Studio) for the LLM, [fastembed](https://github.com/qdrant/fastembed) (`BAAI/bge-small-en-v1.5`) for embeddings, [ChromaDB](https://www.trychroma.com) for vectors, [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration, [trafilatura](https://github.com/adbar/trafilatura) for page extraction and DuckDuckGo ([`ddgs`](https://github.com/deedy5/ddgs)) or a self-hosted [SearXNG](https://github.com/searxng/searxng) for search. No paid API keys.

## Architecture

```
                      ┌──────────────────┐
 user message ──────► │ Ingestion Agent  │  loads any URLs in the message into the session KB
                      └────────┬─────────┘
               only URLs?      │
            ┌──────────────────┤
            ▼                  ▼
            │         ┌──────────────────┐
            │         │  Planner Agent   │  rewrites the question with memory, picks a route
            │         └──┬──────┬──────┬─┘
            │  memory    │      │ KB   │ no KB / "Web search" toggle
            │            │      ▼      │
            │            │ ┌─────────┐ │
            │            │ │Retriever│ │   semantic search over the session's URLs + files
            │            │ └────┬────┘ │
            │            │      ▼      │
            │            │ ┌─────────┐ │
            │            │ │ Grader  │─┼─► not relevant ─┐
            │            │ └────┬────┘ │                 ▼
            │            │      │      └──────► ┌───────────────────┐
            │            │      │               │ Web Research Agent│ search → read top 10 pages
            │            │      │               └─────────┬─────────┘ → rank passages
            ▼            ▼      ▼                         ▼
          ┌───────────────────────────────────────────────────┐
          │ Responder Agent (streams a cited Markdown answer) │
          └───────────────────────────────────────────────────┘
                                   │
                         Memory Agent (background): summarizes older turns
```

Each agent emits trace events that are streamed (SSE) to the UI, so you can see which agents ran and why.

```
backend/   FastAPI app, LangGraph agents (app/agents), loaders, vector store, memory
frontend/  React + Vite + Tailwind chat UI
```

## Quick start (Docker)

```bash
docker compose up --build
```

Open http://localhost:3000. The first start pulls the LLM (`qwen2.5:3b` by default) and the embedding model. Use a bigger model for better answers:

```bash
LLM_MODEL=qwen2.5:7b docker compose up --build
```

> For GPU acceleration add the NVIDIA device reservation to the `ollama` service (see the Ollama Docker docs).

## Local development

Requirements: Python 3.11+, Node 20+, [Ollama](https://ollama.com/download).

```bash
ollama pull qwen2.5:3b

# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# frontend (new terminal)
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

### Configuration

All settings are environment variables (see [`backend/.env.example`](backend/.env.example)):

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `ollama` or `openai_compatible` (vLLM, llama.cpp, LM Studio, LocalAI) |
| `LLM_MODEL` | `qwen2.5:3b` | Model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama URL |
| `OPENAI_BASE_URL` / `OPENAI_API_KEY` | | For `openai_compatible` servers |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Any fastembed model |
| `SEARXNG_URL` | – | Use a self-hosted SearXNG instead of DuckDuckGo |
| `WEB_SEARCH_RESULTS` | `10` | Pages to search & read for web answers |
| `RETRIEVAL_K` / `MIN_SIMILARITY` | `6` / `0.3` | Knowledge-base retrieval |
| `MEMORY_WINDOW` | `10` | Recent messages sent to the LLM; older ones are summarized |
| `DATA_DIR` | `./data` | SQLite DB, Chroma index and model cache |

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Model / search configuration and LLM reachability |
| `GET/POST` | `/api/sessions` | List / create chats |
| `GET/PATCH/DELETE` | `/api/sessions/{id}` | Chat with messages + documents / rename / delete |
| `POST` | `/api/sessions/{id}/urls` | Load a URL (`{"url": "..."}`) |
| `POST` | `/api/sessions/{id}/files` | Upload files (multipart `files`) |
| `GET` | `/api/sessions/{id}/documents` | Loaded URLs & files |
| `DELETE` | `/api/sessions/{id}/documents/{doc_id}` | Remove a URL/file from the knowledge base |
| `POST` | `/api/sessions/{id}/chat` | `{"message": "...", "force_web": false}` → SSE stream of `step`, `token`, `documents_changed`, `error`, `done` events |

Interactive docs: http://localhost:8000/docs

## Tests

```bash
cd backend && ruff check . && pytest      # agents are tested with a fake LLM, embedder and search
cd frontend && npm run lint && npm run build
```

## License

MIT
