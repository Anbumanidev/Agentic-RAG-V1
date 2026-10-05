import asyncio

from app.agents.memory_agent import MemoryAgent


def test_memory_agent_summarizes_every_excluded_message(services):
    services.settings.memory_window = 4
    sid = services.memory.create_session()["id"]
    agent = MemoryAgent(services)
    for i in range(6):
        services.memory.add_message(sid, "user" if i % 2 == 0 else "assistant", f"msg {i}")
    asyncio.run(agent.update(sid))
    assert services.memory.get_session(sid)["summarized_count"] == 2
    services.memory.add_message(sid, "user", "msg 6")
    asyncio.run(agent.update(sid))
    session = services.memory.get_session(sid)
    assert session["summarized_count"] == 3
    assert session["summary"]
