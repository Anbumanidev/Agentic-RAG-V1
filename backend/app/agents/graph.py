"""Wires the agents into a LangGraph state machine.

START -> ingestion -> planner -> retriever -> grader -> responder -> END
             |           |                       |
             |           +--> web_research <-----+  (knowledge not relevant / no docs)
             |           +--> documents -> responder (summaries / overviews of loaded docs)
             |           +--> responder             (conversation memory)
             +--> responder                         (message was only URLs)
"""

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    DocumentAgent,
    GraderAgent,
    IngestionAgent,
    PlannerAgent,
    ResponderAgent,
    RetrieverAgent,
    WebResearchAgent,
)
from app.agents.state import AgentState
from app.services import Services


def _after_ingestion(state: AgentState) -> str:
    return "responder" if state.get("route") == "ingest_only" else "planner"


def _after_planner(state: AgentState) -> str:
    routes = {"knowledge": "retriever", "web": "web_research", "documents": "documents"}
    return routes.get(state["route"], "responder")


def _after_grader(state: AgentState) -> str:
    return "responder" if state.get("relevant") else "web_research"


def build_graph(services: Services):
    graph = StateGraph(AgentState)
    graph.add_node("ingestion", IngestionAgent(services))
    graph.add_node("planner", PlannerAgent(services))
    graph.add_node("retriever", RetrieverAgent(services))
    graph.add_node("documents", DocumentAgent(services))
    graph.add_node("grader", GraderAgent(services))
    graph.add_node("web_research", WebResearchAgent(services))
    graph.add_node("responder", ResponderAgent(services))

    graph.add_edge(START, "ingestion")
    graph.add_conditional_edges("ingestion", _after_ingestion, ["planner", "responder"])
    graph.add_conditional_edges(
        "planner", _after_planner, ["retriever", "web_research", "documents", "responder"]
    )
    graph.add_edge("retriever", "grader")
    graph.add_conditional_edges("grader", _after_grader, ["responder", "web_research"])
    graph.add_edge("web_research", "responder")
    graph.add_edge("documents", "responder")
    graph.add_edge("responder", END)
    return graph.compile()
