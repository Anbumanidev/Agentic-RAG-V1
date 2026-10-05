import operator
from typing import Annotated, Literal, TypedDict

Route = Literal["ingest_only", "conversation", "knowledge", "web", "documents"]


class AgentState(TypedDict, total=False):
    session_id: str
    question: str
    history: list[dict]
    summary: str
    force_web: bool

    ingested: list[dict]
    ingest_errors: list[str]
    just_ingested: bool

    standalone_question: str
    route: Route
    context: list[dict]
    sources: list[dict]
    relevant: bool

    answer: str
    steps: Annotated[list[dict], operator.add]
