import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.prompts import SUMMARY_SYSTEM
from app.agents.utils import history_to_text
from app.services import Services

logger = logging.getLogger(__name__)


class MemoryAgent:
    """Compresses messages that fall out of the short-term window into a running summary."""

    def __init__(self, services: Services):
        self.s = services

    async def update(self, session_id: str) -> None:
        session = self.s.memory.get_session(session_id)
        if not session:
            return
        messages = self.s.memory.get_messages(session_id)
        cutoff = len(messages) - self.s.settings.memory_window
        if cutoff - session["summarized_count"] < 4:
            return
        new = messages[session["summarized_count"] : cutoff]
        prompt = (
            f"Existing summary:\n{session['summary'] or '(none)'}\n\n"
            f"New messages:\n{history_to_text(new, max_chars=1500)}"
        )
        try:
            result = await self.s.llm.ainvoke([SystemMessage(SUMMARY_SYSTEM), HumanMessage(prompt)])
            self.s.memory.update_summary(session_id, str(result.content).strip(), cutoff)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Memory summarization failed: %s", exc)
