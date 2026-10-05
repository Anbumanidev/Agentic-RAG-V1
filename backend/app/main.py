import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agents import build_graph
from app.agents.memory_agent import MemoryAgent
from app.config import get_settings
from app.ingestion import Ingestor
from app.loaders import SUPPORTED_EXTENSIONS, LoaderError
from app.schemas import ChatRequest, RenameRequest, UrlRequest
from app.services import Services, build_services

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("agentic_rag")


def create_app(services: Services | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        s = services or build_services(get_settings())
        app.state.services = s
        app.state.graph = build_graph(s)
        app.state.ingestor = Ingestor(s)
        app.state.memory_agent = MemoryAgent(s)
        app.state.background = set()
        yield

    app = FastAPI(title="Agentic RAG", version="0.1.0", lifespan=lifespan)
    settings = services.settings if services else get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def svc(request: Request) -> Services:
        return request.app.state.services

    def require_session(request: Request, session_id: str) -> dict:
        session = svc(request).memory.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    @app.get("/api/health")
    async def health(request: Request):
        s = svc(request)
        llm_ok = True
        if s.settings.llm_provider == "ollama":
            try:
                async with httpx.AsyncClient(timeout=3) as client:
                    llm_ok = (await client.get(f"{s.settings.ollama_base_url}/api/tags")).is_success
            except httpx.HTTPError:
                llm_ok = False
        return {
            "status": "ok",
            "llm_provider": s.settings.llm_provider,
            "llm_model": s.settings.llm_model,
            "llm_reachable": llm_ok,
            "embedding_model": s.settings.embedding_model,
            "web_search": "searxng" if s.settings.searxng_url else "duckduckgo",
            "supported_files": sorted(SUPPORTED_EXTENSIONS),
        }

    # Sessions -------------------------------------------------------------
    @app.get("/api/sessions")
    async def list_sessions(request: Request):
        return svc(request).memory.list_sessions()

    @app.post("/api/sessions", status_code=201)
    async def create_session(request: Request):
        return svc(request).memory.create_session()

    @app.get("/api/sessions/{session_id}")
    async def get_session(request: Request, session_id: str):
        session = require_session(request, session_id)
        memory = svc(request).memory
        return {
            **session,
            "messages": memory.get_messages(session_id),
            "documents": memory.list_documents(session_id),
        }

    @app.patch("/api/sessions/{session_id}")
    async def rename_session(request: Request, session_id: str, body: RenameRequest):
        require_session(request, session_id)
        svc(request).memory.rename_session(session_id, body.title)
        return svc(request).memory.get_session(session_id)

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(request: Request, session_id: str):
        require_session(request, session_id)
        s = svc(request)
        await asyncio.to_thread(s.store.delete_session, session_id)
        s.memory.delete_session(session_id)

    # Knowledge ------------------------------------------------------------
    @app.get("/api/sessions/{session_id}/documents")
    async def list_documents(request: Request, session_id: str):
        require_session(request, session_id)
        return svc(request).memory.list_documents(session_id)

    @app.post("/api/sessions/{session_id}/urls", status_code=201)
    async def add_url(request: Request, session_id: str, body: UrlRequest):
        require_session(request, session_id)
        try:
            doc = await request.app.state.ingestor.ingest_url(session_id, body.url.strip())
        except LoaderError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        doc.pop("preview", None)
        return doc

    @app.post("/api/sessions/{session_id}/files", status_code=201)
    async def add_files(
        request: Request, session_id: str, files: Annotated[list[UploadFile], File()]
    ):
        require_session(request, session_id)
        limit = svc(request).settings.max_upload_mb * 1024 * 1024
        documents, errors = [], []
        for upload in files:
            data = await upload.read()
            name = upload.filename or "upload"
            if len(data) > limit:
                errors.append(f"{name}: larger than {limit // (1024 * 1024)} MB")
                continue
            try:
                doc = await request.app.state.ingestor.ingest_file(session_id, name, data)
                doc.pop("preview", None)
                documents.append(doc)
            except LoaderError as exc:
                errors.append(str(exc))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to ingest %s", name)
                errors.append(f"{name}: {exc}")
        if not documents and errors:
            raise HTTPException(status_code=400, detail="; ".join(errors))
        return {"documents": documents, "errors": errors}

    @app.delete("/api/sessions/{session_id}/documents/{document_id}", status_code=204)
    async def delete_document(request: Request, session_id: str, document_id: str):
        require_session(request, session_id)
        s = svc(request)
        doc = s.memory.get_document(document_id)
        if not doc or doc["session_id"] != session_id:
            raise HTTPException(status_code=404, detail="Document not found")
        await asyncio.to_thread(s.store.delete_document, session_id, document_id)
        s.memory.delete_document(document_id)

    # Chat -----------------------------------------------------------------
    @app.post("/api/sessions/{session_id}/chat")
    async def chat(request: Request, session_id: str, body: ChatRequest):
        session = require_session(request, session_id)
        s = svc(request)
        graph = request.app.state.graph

        history = [
            {"role": m["role"], "content": m["content"]} for m in s.memory.get_messages(session_id)
        ]
        if not history and session["title"] == "New chat":
            title = body.message.strip().replace("\n", " ")
            s.memory.rename_session(session_id, title[:60] + ("…" if len(title) > 60 else ""))
        s.memory.add_message(session_id, "user", body.message)

        state = {
            "session_id": session_id,
            "question": body.message,
            "history": history,
            "summary": session["summary"],
            "force_web": body.force_web,
            "steps": [],
        }

        def sse(event: dict) -> str:
            return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        async def stream() -> AsyncIterator[str]:
            final: dict = {}
            try:
                async for mode, chunk in graph.astream(state, stream_mode=["custom", "values"]):
                    if mode == "custom":
                        yield sse(chunk)
                    else:
                        final = chunk
            except Exception as exc:  # noqa: BLE001
                logger.exception("Agent graph failed")
                yield sse({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
                final.setdefault("answer", "")
                final["error"] = str(exc)

            answer = final.get("answer") or (
                "Sorry, something went wrong while answering." if final.get("error") else ""
            )
            meta = {
                "route": final.get("route"),
                "sources": final.get("sources", []),
                "steps": final.get("steps", []),
                "ingested": [
                    {k: d[k] for k in ("id", "title", "source", "kind", "chunks")}
                    for d in final.get("ingested", [])
                ],
            }
            message_id = s.memory.add_message(session_id, "assistant", answer, meta)
            yield sse({"type": "done", "message_id": message_id, "answer": answer, **meta})

            task = asyncio.create_task(request.app.state.memory_agent.update(session_id))
            request.app.state.background.add(task)
            task.add_done_callback(request.app.state.background.discard)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()
