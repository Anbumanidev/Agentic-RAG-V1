import json
import re

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.config import get_stream_writer


def emit(event: dict) -> None:
    """Send a custom event to the client stream (no-op outside of streaming)."""
    try:
        writer = get_stream_writer()
    except Exception:  # noqa: BLE001 - not running inside a streaming graph
        return
    if writer:
        writer(event)


def step(agent: str, detail: str, **extra) -> dict:
    item = {"agent": agent, "detail": detail, **extra}
    emit({"type": "step", **item})
    return item


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def history_to_messages(history: list[dict]) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    for item in history:
        if item["role"] == "user":
            messages.append(HumanMessage(item["content"]))
        elif item["role"] == "assistant":
            messages.append(AIMessage(item["content"]))
    return messages


def history_to_text(history: list[dict], max_chars: int = 600) -> str:
    lines = []
    for item in history:
        content = item["content"]
        if len(content) > max_chars:
            content = content[:max_chars] + "..."
        lines.append(f"{item['role'].upper()}: {content}")
    return "\n".join(lines)
