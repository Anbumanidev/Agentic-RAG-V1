"""The individual agents that make up the RAG graph."""

import asyncio
import logging
import re
from collections import defaultdict

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import (
    GRADER_SYSTEM,
    PLANNER_SYSTEM,
    RESPONDER_SYSTEM,
    ROUTE_INSTRUCTIONS,
)
from app.agents.state import AgentState
from app.agents.utils import emit, history_to_messages, history_to_text, parse_json, step
from app.embeddings import cosine_similarity
from app.ingestion import Ingestor
from app.loaders import extract_urls, split_text, strip_urls
from app.services import Services

logger = logging.getLogger(__name__)

OVERVIEW_RE = re.compile(
    r"\b(summari[sz]e|summary|overview|tl;?dr|key points|main points|gist|what is (it|this)"
    r" about|what('s| is) in)\b",
    re.IGNORECASE,
)
DOC_WORD_RE = re.compile(
    r"\b(doc|docs|document|documents|file|files|pdf|attachment|attached|upload|uploaded|url|"
    r"page|article|it|this|these|them)\b",
    re.IGNORECASE,
)


def document_catalog(docs: list[dict]) -> str:
    return "\n".join(f"- {d['title']} ({d['kind']}, {d['chunks']} chunks)" for d in docs)


class IngestionAgent:
    """Detects URLs in the user's message and loads them into the knowledge base."""

    name = "Ingestion Agent"

    def __init__(self, services: Services):
        self.ingestor = Ingestor(services)

    async def __call__(self, state: AgentState) -> dict:
        urls = extract_urls(state["question"])
        if not urls:
            return {"ingested": [], "ingest_errors": [], "just_ingested": False}

        steps = [step(self.name, f"Loading {len(urls)} URL(s)")]
        results = await asyncio.gather(
            *(self.ingestor.ingest_url(state["session_id"], u) for u in urls),
            return_exceptions=True,
        )
        ingested, errors = [], []
        for url, result in zip(urls, results, strict=True):
            if isinstance(result, Exception):
                errors.append(f"{url}: {result}")
                steps.append(step(self.name, f"Failed to load {url}", status="error"))
            else:
                ingested.append(result)
                steps.append(
                    step(self.name, f"Loaded '{result['title']}' ({result['chunks']} chunks)")
                )
        if ingested:
            emit({"type": "documents_changed"})

        residual = strip_urls(state["question"])
        update: dict = {
            "ingested": ingested,
            "ingest_errors": errors,
            "just_ingested": bool(ingested),
            "steps": steps,
        }
        if len(residual) < 4:
            update["route"] = "ingest_only"
            update["standalone_question"] = state["question"]
        return update


class PlannerAgent:
    """Rewrites the question using memory and decides which agent should handle it."""

    name = "Planner Agent"

    def __init__(self, services: Services):
        self.s = services

    async def __call__(self, state: AgentState) -> dict:
        question = state["question"]
        docs = self.s.memory.list_documents(state["session_id"])
        has_docs = bool(docs)

        prompt = (
            f"Loaded documents:\n{document_catalog(docs) or '(none)'}\n\n"
            f"Conversation summary: {state.get('summary') or '(none)'}\n\n"
            f"Recent conversation:\n{history_to_text(state.get('history', [])[-6:]) or '(none)'}"
            f"\n\nLatest user message: {question}"
        )
        standalone, decision = question, "research"
        try:
            result = await self.s.json_llm.ainvoke(
                [SystemMessage(PLANNER_SYSTEM), HumanMessage(prompt)]
            )
            data = parse_json(result.content)
            standalone = (data.get("standalone_question") or question).strip()
            if data.get("route") in {"conversation", "documents"}:
                decision = data["route"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Planner failed, falling back to research: %s", exc)

        clean = strip_urls(question)
        names_doc = any(d["title"].lower() in clean.lower() for d in docs)
        if has_docs and OVERVIEW_RE.search(clean) and (DOC_WORD_RE.search(clean) or names_doc):
            decision = "documents"
        elif decision == "documents" and not has_docs:
            decision = "research"

        if state.get("just_ingested"):
            standalone = strip_urls(standalone) or standalone
        if state.get("force_web"):
            route = "web"
        elif decision == "documents":
            route = "documents"
        elif state.get("just_ingested"):
            route = "ingest_only" if decision == "conversation" else "knowledge"
        elif decision == "conversation":
            route = "conversation"
        elif has_docs:
            route = "knowledge"
        else:
            route = "web"

        labels = {
            "knowledge": "searching your knowledge base",
            "web": "researching on the web",
            "conversation": "answering from conversation memory",
            "ingest_only": "summarizing the newly loaded content",
            "documents": "summarizing your documents",
        }
        return {
            "standalone_question": standalone,
            "route": route,
            "steps": [step(self.name, f'Plan: {labels[route]} — "{standalone}"', route=route)],
        }


class RetrieverAgent:
    """Semantic search over the session's URLs and files."""

    name = "Retriever Agent"

    def __init__(self, services: Services):
        self.s = services

    async def __call__(self, state: AgentState) -> dict:
        query = state.get("standalone_question") or state["question"]
        chunks = await asyncio.to_thread(
            self.s.store.search, state["session_id"], query, self.s.settings.retrieval_k
        )
        threshold = 0.0 if state.get("just_ingested") else self.s.settings.min_similarity
        chunks = [c for c in chunks if c.score >= threshold]

        source_index: dict[str, int] = {}
        sources, context = [], []
        for chunk in chunks:
            src = chunk.metadata.get("source", "unknown")
            if src not in source_index:
                source_index[src] = len(sources) + 1
                sources.append(
                    {
                        "index": source_index[src],
                        "title": chunk.metadata.get("title", src),
                        "url": src if src.startswith("http") else None,
                        "kind": chunk.metadata.get("kind", "file"),
                        "score": round(chunk.score, 3),
                    }
                )
            context.append(
                {"index": source_index[src], "text": chunk.text, "score": round(chunk.score, 3)}
            )
        return {
            "context": context,
            "sources": sources,
            "steps": [
                step(self.name, f"Retrieved {len(context)} chunk(s) from {len(sources)} source(s)")
            ],
        }


class DocumentAgent:
    """Gathers excerpts spanning whole documents for summaries and overviews."""

    name = "Document Agent"
    max_docs = 6
    chunk_budget = 14

    def __init__(self, services: Services):
        self.s = services

    def _select(self, state: AgentState, docs: list[dict]) -> list[dict]:
        question = strip_urls(state["question"]).lower()
        named = [
            d
            for d in docs
            if d["title"].lower() in question
            or d["title"].rsplit(".", 1)[0].lower() in question
            or d["source"].lower() in state["question"].lower()
        ]
        if named:
            return named
        if state.get("ingested"):
            ids = {d["id"] for d in state["ingested"]}
            return [d for d in docs if d["id"] in ids]
        if re.search(r"\b(all|every|documents|files|docs|them|these)\b", question):
            return docs
        for message in reversed(self.s.memory.get_messages(state["session_id"])):
            ids = {a["id"] for a in message["meta"].get("attachments", [])}
            latest = [d for d in docs if d["id"] in ids]
            if latest:
                return latest
        return docs[-1:]

    async def __call__(self, state: AgentState) -> dict:
        docs = self.s.memory.list_documents(state["session_id"])
        selected = self._select(state, docs)[-self.max_docs :]
        per_doc = max(2, self.chunk_budget // max(1, len(selected)))
        sources, context = [], []
        for i, doc in enumerate(selected, start=1):
            chunks = await asyncio.to_thread(
                self.s.store.get_document_chunks, state["session_id"], doc["id"], per_doc
            )
            sources.append(
                {
                    "index": i,
                    "title": doc["title"],
                    "url": doc["source"] if doc["source"].startswith("http") else None,
                    "kind": doc["kind"],
                }
            )
            context += [{"index": i, "text": c.text} for c in chunks]
        titles = ", ".join(d["title"] for d in selected) or "none"
        return {
            "context": context,
            "sources": sources,
            "steps": [step(self.name, f"Reading {len(selected)} document(s): {titles}")],
        }


class GraderAgent:
    """Judges whether the retrieved knowledge can answer the question."""

    name = "Grader Agent"

    def __init__(self, services: Services):
        self.s = services

    async def __call__(self, state: AgentState) -> dict:
        context = state.get("context") or []
        if not context:
            return {
                "relevant": False,
                "steps": [step(self.name, "No relevant knowledge found — handing off to web")],
            }
        snippets = "\n\n".join(f"[{c['index']}] {c['text'][:700]}" for c in context[:4])
        prompt = f"Question: {state['standalone_question']}\n\nContext:\n{snippets}"
        relevant, reason = True, ""
        try:
            result = await self.s.json_llm.ainvoke(
                [SystemMessage(GRADER_SYSTEM), HumanMessage(prompt)]
            )
            data = parse_json(result.content)
            value = data.get("relevant", True)
            relevant = value if isinstance(value, bool) else str(value).lower() == "true"
            reason = data.get("reason", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Grader failed, assuming relevant: %s", exc)

        detail = (
            "Knowledge base can answer this"
            if relevant
            else "Knowledge base is not relevant — handing off to web"
        )
        if reason:
            detail += f" ({reason})"
        update: dict = {"relevant": relevant, "steps": [step(self.name, detail)]}
        if not relevant:
            update["route"] = "web"
            update["context"], update["sources"] = [], []
        return update


class WebResearchAgent:
    """Searches the web, reads the top pages and keeps the most relevant passages."""

    name = "Web Research Agent"

    def __init__(self, services: Services):
        self.s = services

    async def __call__(self, state: AgentState) -> dict:
        cfg = self.s.settings
        query = state.get("standalone_question") or state["question"]
        steps = [step(self.name, f'Searching the web for "{query}"')]
        results = await self.s.web.search(query, cfg.web_search_results)
        if not results:
            steps.append(step(self.name, "No web results found", status="error"))
            return {"route": "web", "context": [], "sources": [], "steps": steps}

        steps.append(step(self.name, f"Reading top {len(results)} pages"))
        pages = await self.s.web.fetch_pages(results, cfg.web_max_chars_per_page)
        read = sum(p.fetched for p in pages)
        steps.append(step(self.name, f"Read {read}/{len(pages)} pages, ranking passages"))

        passages: list[tuple[int, str]] = []
        for i, page in enumerate(pages, start=1):
            for chunk in split_text(page.content, cfg.chunk_size, cfg.chunk_overlap)[:30]:
                passages.append((i, chunk))

        context: list[dict] = []
        if passages:
            vectors = await asyncio.to_thread(
                self.s.embedder.embed, [query] + [text for _, text in passages]
            )
            scores = cosine_similarity(vectors[0], vectors[1:])
            ranked = sorted(zip(scores, passages, strict=True), key=lambda x: x[0], reverse=True)
            per_page: dict[int, int] = defaultdict(int)
            for score, (index, text) in ranked:
                if per_page[index] >= 2:
                    continue
                per_page[index] += 1
                context.append({"index": index, "text": text, "score": round(float(score), 3)})
                if len(context) >= cfg.web_context_chunks:
                    break
            context.sort(key=lambda c: c["index"])

        used = {c["index"] for c in context}
        sources = [
            {
                "index": i,
                "title": page.title or page.url,
                "url": page.url,
                "kind": "web",
                "snippet": page.snippet,
                "fetched": page.fetched,
                "used": i in used,
            }
            for i, page in enumerate(pages, start=1)
        ]
        return {"route": "web", "context": context, "sources": sources, "steps": steps}


class ResponderAgent:
    """Writes the final answer, streaming tokens to the client."""

    name = "Responder Agent"

    def __init__(self, services: Services):
        self.s = services

    async def __call__(self, state: AgentState) -> dict:
        route = state.get("route", "conversation")
        steps = [step(self.name, "Writing the answer")]
        sources = state.get("sources") or []
        context = state.get("context") or []

        if route == "ingest_only":
            if not state.get("ingested"):
                errors = "\n".join(f"- {e}" for e in state.get("ingest_errors", []))
                answer = f"I couldn't load the content you sent:\n\n{errors}"
                emit({"type": "token", "content": answer})
                return {"answer": answer, "sources": [], "steps": steps}
            sources, context = [], []
            for i, doc in enumerate(state["ingested"], start=1):
                sources.append(
                    {"index": i, "title": doc["title"], "url": doc["source"], "kind": doc["kind"]}
                )
                context += [{"index": i, "text": t} for t in doc.get("preview", [])]

        system = [RESPONDER_SYSTEM, ROUTE_INSTRUCTIONS[route]]
        if state.get("summary"):
            system.append(f"Summary of earlier conversation:\n{state['summary']}")
        if state.get("ingest_errors"):
            system.append("Some URLs failed to load: " + "; ".join(state["ingest_errors"]))
        if route != "web":
            docs = self.s.memory.list_documents(state["session_id"])
            if docs:
                system.append(
                    "Documents loaded in this chat (oldest first):\n" + document_catalog(docs)
                )
        if route in {"knowledge", "web", "ingest_only", "documents"}:
            titles = {s["index"]: s["title"] for s in sources}
            blocks = [
                f"[{c['index']}] ({titles.get(c['index'], '')})\n{c['text']}" for c in context
            ]
            system.append("CONTEXT:\n" + ("\n\n".join(blocks) if blocks else "(no context found)"))

        window = self.s.settings.memory_window
        messages = [
            SystemMessage("\n\n".join(system)),
            *history_to_messages(state.get("history", [])[-window:]),
            HumanMessage(state["question"]),
        ]

        parts: list[str] = []
        async for chunk in self.s.llm.astream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                parts.append(text)
                emit({"type": "token", "content": text})
        return {"answer": "".join(parts), "sources": sources, "steps": steps}
