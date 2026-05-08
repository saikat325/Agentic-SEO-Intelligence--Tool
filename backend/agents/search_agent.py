from typing import TypedDict, List, Dict, Any, Annotated
import operator
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from core.config import get_settings
from core.vectorstore import semantic_search

settings = get_settings()


# ─── State Schema ────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    repo_id: str
    query: str
    retrieved_chunks: List[Dict[str, Any]]
    analysis: str
    final_answer: Dict[str, Any]
    messages: Annotated[List, operator.add]


# ─── LLM ─────────────────────────────────────────────────────────────────────

def get_llm():
    return ChatGroq(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        temperature=0.1,
        max_tokens=2048,
    )


# ─── Node: Retrieve ───────────────────────────────────────────────────────────

def retrieve_node(state: AgentState) -> AgentState:
    """Retrieve top-k semantically relevant chunks from the vector store."""
    chunks = semantic_search(
        repo_id=state["repo_id"],
        query=state["query"],
        top_k=10,
    )
    return {**state, "retrieved_chunks": chunks}


# ─── Node: Analyse ────────────────────────────────────────────────────────────

def analyse_node(state: AgentState) -> AgentState:
    """Use Groq LLM to analyse retrieved chunks and form a precise answer."""
    llm = get_llm()
    chunks = state["retrieved_chunks"]

    if not chunks:
        return {
            **state,
            "analysis": "No relevant code found.",
            "final_answer": {
                "answer": "No relevant code was found for your query.",
                "results": [],
            },
        }

    # Build context block
    context_parts = []
    for i, c in enumerate(chunks[:8]):
        context_parts.append(
            f"[Result {i+1}]\n"
            f"File: {c['file_path']} | Lines: {c['start_line']}-{c['end_line']} "
            f"| Symbol: {c['symbol_name'] or 'N/A'} ({c['symbol_type'] or 'N/A'})\n"
            f"Relevance Score: {c['score']}\n"
            f"```{c['language']}\n{c['text']}\n```"
        )
    context = "\n\n".join(context_parts)

    system_prompt = """You are an expert code navigator and software architect.
Your task is to answer questions about a GitHub codebase by analysing the provided code snippets.

Rules:
1. Always cite the exact file path and line numbers.
2. If a function is found, name it explicitly.
3. Explain HOW the code works, not just WHERE it is.
4. If multiple relevant locations exist, list ALL of them.
5. Be concise but precise — developers need actionable answers.
6. Respond in structured markdown with clear sections."""

    user_prompt = f"""Question: {state['query']}

Retrieved Code Snippets:
{context}

Provide a structured answer with:
- **Direct Answer**: What exactly implements this / where it is
- **File Locations**: file path + line numbers for each relevant result
- **Code Analysis**: Brief explanation of what the code does
- **Related Functions/Classes**: Any other relevant symbols found"""

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    analysis = response.content

    # Build structured result list
    results = [
        {
            "file_path": c["file_path"],
            "start_line": c["start_line"],
            "end_line": c["end_line"],
            "symbol_name": c["symbol_name"],
            "symbol_type": c["symbol_type"],
            "score": c["score"],
            "snippet": c["text"][:500] + ("..." if len(c["text"]) > 500 else ""),
        }
        for c in chunks
    ]

    return {
        **state,
        "analysis": analysis,
        "final_answer": {
            "answer": analysis,
            "results": results,
            "query": state["query"],
        },
        "messages": state["messages"] + [AIMessage(content=analysis)],
    }


# ─── Build LangGraph ──────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("analyse", analyse_node)
    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "analyse")
    graph.add_edge("analyse", END)
    return graph.compile()


_graph = None

def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_query(repo_id: str, query: str) -> Dict[str, Any]:
    """Run the full LangGraph agent pipeline for a user query."""
    graph = get_graph()
    initial_state: AgentState = {
        "repo_id": repo_id,
        "query": query,
        "retrieved_chunks": [],
        "analysis": "",
        "final_answer": {},
        "messages": [HumanMessage(content=query)],
    }
    result = graph.invoke(initial_state)
    return result["final_answer"]
