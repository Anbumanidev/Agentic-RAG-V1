"""Turns URLs and files into searchable chunks in a session's knowledge base."""

import asyncio

from app.loaders import LoadedDocument, fetch_url, load_file, split_text
from app.services import Services


class Ingestor:
    def __init__(self, services: Services):
        self.s = services

    async def _index(self, session_id: str, kind: str, doc: LoadedDocument) -> dict:
        existing = self.s.memory.find_document(session_id, doc.source)
        if existing:
            await asyncio.to_thread(self.s.store.delete_document, session_id, existing["id"])
            self.s.memory.delete_document(existing["id"])

        chunks = split_text(doc.text, self.s.settings.chunk_size, self.s.settings.chunk_overlap)
        record = self.s.memory.add_document(
            session_id, kind, doc.source, doc.title, len(chunks), len(doc.text)
        )
        metadatas = [
            {
                "document_id": record["id"],
                "kind": kind,
                "source": doc.source,
                "title": doc.title,
                "chunk": i,
            }
            for i in range(len(chunks))
        ]
        await asyncio.to_thread(self.s.store.add, session_id, chunks, metadatas)
        record["preview"] = chunks[:4]
        return record

    async def ingest_url(self, session_id: str, url: str) -> dict:
        doc = await fetch_url(url, timeout=self.s.settings.web_fetch_timeout)
        return await self._index(session_id, "url", doc)

    async def ingest_file(self, session_id: str, filename: str, data: bytes) -> dict:
        doc = await asyncio.to_thread(load_file, filename, data)
        return await self._index(session_id, "file", doc)
