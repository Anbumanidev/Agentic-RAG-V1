from app import loaders
from app.loaders import LoadedDocument
from tests.conftest import read_events


def new_session(client) -> str:
    return client.post("/api/sessions").json()["id"]


def chat(client, sid, message, **extra):
    resp = client.post(f"/api/sessions/{sid}/chat", json={"message": message, **extra})
    assert resp.status_code == 200
    events = read_events(resp)
    assert events[-1]["type"] == "done"
    return events


def test_health(client):
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert ".pdf" in data["supported_files"]


def test_session_crud(client):
    sid = new_session(client)
    assert any(s["id"] == sid for s in client.get("/api/sessions").json())
    client.patch(f"/api/sessions/{sid}", json={"title": "Renamed"})
    assert client.get(f"/api/sessions/{sid}").json()["title"] == "Renamed"
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404


def test_file_upload_then_question_uses_knowledge(client):
    sid = new_session(client)
    resp = client.post(
        f"/api/sessions/{sid}/files",
        files=[("files", ("notes.txt", b"The secret code for the vault is 42.", "text/plain"))],
    )
    assert resp.status_code == 201
    assert resp.json()["documents"][0]["title"] == "notes.txt"

    events = chat(client, sid, "What is the secret code for the vault?")
    done = events[-1]
    assert done["route"] == "knowledge"
    assert "42" in done["answer"]
    assert done["sources"][0]["title"] == "notes.txt"
    agents = [e["agent"] for e in events if e["type"] == "step"]
    assert agents[:3] == ["Planner Agent", "Retriever Agent", "Grader Agent"]
    assert any(e["type"] == "token" for e in events)


def test_irrelevant_question_falls_back_to_web(client, services):
    sid = new_session(client)
    client.post(
        f"/api/sessions/{sid}/files",
        files=[
            ("files", ("notes.txt", b"Bananas are yellow fruit rich in potassium.", "text/plain"))
        ],
    )
    done = chat(client, sid, "Why are bananas the capital of Mars?")[-1]
    assert done["route"] == "web"
    assert len(done["sources"]) == 10
    assert services.web.queries


def test_out_of_box_question_without_docs_uses_web(client, services):
    sid = new_session(client)
    events = chat(client, sid, "What is the capital of Mars?")
    done = events[-1]
    assert done["route"] == "web"
    assert "Olympus" in done["answer"]
    assert any("Reading top 10 pages" in e.get("detail", "") for e in events)


def test_force_web(client, services):
    sid = new_session(client)
    client.post(
        f"/api/sessions/{sid}/files",
        files=[("files", ("a.md", b"The secret code for the vault is 42.", "text/markdown"))],
    )
    done = chat(client, sid, "What is the secret code?", force_web=True)[-1]
    assert done["route"] == "web"


def test_url_in_message_is_ingested_and_answered(client, monkeypatch):
    async def fake_fetch(url, client=None, timeout=15.0):
        return LoadedDocument(title="Vault docs", source=url, text="The secret code is 42.")

    monkeypatch.setattr(loaders, "fetch_url", fake_fetch)
    monkeypatch.setattr("app.ingestion.fetch_url", fake_fetch)
    sid = new_session(client)

    done = chat(client, sid, "https://example.org/vault")[-1]
    assert done["route"] is None or done["ingested"]
    assert done["ingested"][0]["title"] == "Vault docs"
    assert client.get(f"/api/sessions/{sid}/documents").json()[0]["kind"] == "url"

    done = chat(client, sid, "What is the secret code?")[-1]
    assert done["route"] == "knowledge"
    assert done["sources"][0]["url"] == "https://example.org/vault"


def test_add_url_endpoint(client, monkeypatch):
    async def fake_fetch(url, client=None, timeout=15.0):
        return LoadedDocument(title="Page", source=url, text="hello " * 500)

    monkeypatch.setattr("app.ingestion.fetch_url", fake_fetch)
    sid = new_session(client)
    resp = client.post(f"/api/sessions/{sid}/urls", json={"url": "https://example.org"})
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["chunks"] > 1
    assert client.delete(f"/api/sessions/{sid}/documents/{doc['id']}").status_code == 204
    assert client.get(f"/api/sessions/{sid}/documents").json() == []


def test_conversation_memory(client):
    sid = new_session(client)
    chat(client, sid, "Hi, I am Anbu")
    done = chat(client, sid, "What is my name?")[-1]
    assert done["route"] == "conversation"
    assert "Anbu" in done["answer"]
    messages = client.get(f"/api/sessions/{sid}").json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[-1]["meta"]["route"] == "conversation"


def test_unsupported_file_rejected(client):
    sid = new_session(client)
    resp = client.post(
        f"/api/sessions/{sid}/files",
        files=[("files", ("x.exe", b"MZ", "application/octet-stream"))],
    )
    assert resp.status_code == 400


def test_force_web_applies_to_url_questions(client, monkeypatch):
    async def fake_fetch(url, client=None, timeout=15.0):
        return LoadedDocument(title="Vault docs", source=url, text="The secret code is 42.")

    monkeypatch.setattr("app.ingestion.fetch_url", fake_fetch)
    sid = new_session(client)
    done = chat(client, sid, "https://example.org/vault What is the secret code?", force_web=True)[
        -1
    ]
    assert done["ingested"]
    assert done["route"] == "web"


def test_unrelated_question_with_new_url_falls_back_to_web(client, monkeypatch):
    async def fake_fetch(url, client=None, timeout=15.0):
        return LoadedDocument(title="Bananas", source=url, text="Bananas are yellow fruit.")

    monkeypatch.setattr("app.ingestion.fetch_url", fake_fetch)
    sid = new_session(client)
    done = chat(client, sid, "https://example.org/bananas why are bananas the capital of Mars?")[-1]
    assert done["route"] == "web"


def test_private_urls_are_rejected(client):
    sid = new_session(client)
    for url in ("http://127.0.0.1:8000/api/sessions", "http://localhost/", "file:///etc/passwd"):
        resp = client.post(f"/api/sessions/{sid}/urls", json={"url": url})
        assert resp.status_code == 400, url
