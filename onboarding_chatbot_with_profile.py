from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages 
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os
import re

from langgraph.checkpoint.postgres import PostgresSaver
import psycopg

#------------------------ New Function
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

# -------- Configs for compact memory --------
LAST_K = 6  # how many recent messages to send each turn
MAX_SUMMARY_CHARS = 2000  # keep the summary bounded

NAME_PATTERNS = [
    re.compile(r"\bmy name is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", re.I),
    re.compile(r"\bi am\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", re.I),
    re.compile(r"\bthis is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b", re.I),
]

def extract_name(text: str) -> Optional[str]:
    for pat in NAME_PATTERNS:
        m = pat.search(text.strip())
        if m:
            # clean trailing punctuation
            name = m.group(1).strip().rstrip(".!?,;:")
            # sanity check: avoid capturing generic words
            if len(name.split()) <= 4:
                return name
    return None

def build_system_block(profile: dict, summary: str) -> SystemMessage:
    # very compact system context that’s re-sent each turn
    parts = []
    if profile:
        parts.append(f"Known user profile: {profile}.")
    if summary:
        parts.append(f"Conversation summary: {summary}")
    if not parts:
        parts.append("No prior profile or summary.")
    return SystemMessage(content=" ".join(parts))

def trim_messages(msgs: list[BaseMessage], k: int = LAST_K) -> list[BaseMessage]:
    return msgs[-k:]

def clip_summary(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    # keep both head and tail
    head = text[: limit // 2]
    tail = text[- limit // 2 :]
    return head + " … " + tail

def main():
    POOL: ConnectionPool = ConnectionPool(
        conninfo=os.getenv("DATABASE_URL"),
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
    )

    @tool
    def assign_seating_space(seat_type: Optional[str] = None) -> dict:
        """
        Assign an available seat to an employee with optional seat_type.
        Returns {"ok": bool, "seat_id": int?, "seat_type": str?, "message": str?}
        """
        sql = """
            SELECT ss.seat_id, ss.seat_type
            FROM onboarding.seating_space ss
            WHERE ss.employee_id IS NULL
              AND (%(seat_type)s::text IS NULL OR ss.seat_type = %(seat_type)s::text)
            ORDER BY random()
            LIMIT 1;
        """
        with POOL.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"seat_type": seat_type})
                row = cur.fetchone()
                if not row:
                    return {"ok": False, "message": "No available seating space."}
                return {"ok": True, "seat_id": row["seat_id"], "seat_type": row["seat_type"]}

    tools = [assign_seating_space]
    
    print(tools)

    DSN = os.getenv("DATABASE_URL")
    conn = psycopg.connect(DSN)
    conn.autocommit = True
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()

    llm = model = ChatOpenAI(
        base_url=os.getenv("JETSTREAM_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("JETSTREAM_MODEL"),
        temperature=0.2,
    )
    llm_bind = llm.bind_tools(tools)

    # -------- Compact-memory state --------
    class State(TypedDict):
        messages: Annotated[list[BaseMessage], add_messages]
        username: str
        profile: dict
        summary: str

    # ----- LLM turn: inject compact context (profile + summary + last_k) -----
    def process(s: State) -> State:
        last_k = trim_messages(s["messages"], LAST_K)
        sys = build_system_block(s.get("profile", {}), s.get("summary", ""))
        prompt_msgs = [sys] + last_k
        # print("prompt_msgs: ", prompt_msgs)
        ai = llm_bind.invoke(prompt_msgs)
        return {"messages": [ai if isinstance(ai, AIMessage) else AIMessage(content=ai.content)]}

    # ----- Should call tools? -----
    def should_continue(state: State):
        last_message = state["messages"][-1]
        if getattr(last_message, "tool_calls", None):
            return "tool_node"
        return "memory_update"

    # ----- After the LLM (and after tools), update memory cheaply -----
    def memory_update(s: State) -> State:
        # 1) Lightweight entity extraction: capture name once
        try:
            # look at the latest human message
            # if the very last message is AI, also peek one before that
            recent_human = None
            for m in reversed(s["messages"][-3:]):
                if isinstance(m, HumanMessage):
                    recent_human = m
                    break
            if recent_human:
                name = extract_name(recent_human.content or "")
                if name:
                    prof = dict(s.get("profile") or {})
                    # only set if missing or different
                    if prof.get("name") != name:
                        prof["name"] = name
                        s["profile"] = prof
        except Exception:
            pass

        # 2) Update a compact summary using the last small window
        #    We’ll synthesize a very short summary with the same LLM (cheap prompt).
        #    This runs on the same model for simplicity; you can swap in a cheaper model.
        recent = trim_messages(s["messages"], 4)  # only 4 messages to summarize
        if recent:
            sys = SystemMessage(
                content=(
                    "You are a summarizer. Write a terse update to an existing "
                    "running summary in <150 words, focusing on facts and decisions. "
                    "Do NOT restate the whole chat. Keep it compact."
                )
            )
            old_summary = s.get("summary", "")
            # We pass the existing summary to be updated, not replaced.
            user_sum = HumanMessage(
                content=(
                    f"Existing summary:\n{old_summary}\n\n"
                    f"Recent messages to fold in:\n" +
                    "\n---\n".join(
                        f"{m.type.upper()}: {getattr(m,'content','')}" for m in recent
                    ) +
                    "\n\nReturn only the updated summary."
                )
            )
            try:
                new_sum_msg = llm.invoke([sys, user_sum])
                new_summary = getattr(new_sum_msg, "content", "") or ""
                s["summary"] = clip_summary(new_summary, MAX_SUMMARY_CHARS)
            except Exception:
                # Fallback: very cheap heuristic if summarization fails
                tail = " ".join([getattr(m, "content", "") for m in recent if getattr(m, "content", "")])
                merged = (old_summary + " " + tail).strip()
                s["summary"] = clip_summary(merged, MAX_SUMMARY_CHARS)

        return {"profile": s.get("profile", {}), "summary": s.get("summary", "")}

    # -------- Build graph --------
    graph = StateGraph(State)
    graph.add_node("main_llm", process)
    graph.add_node("tool_node", ToolNode(tools))
    graph.add_node("memory_update", memory_update)

    graph.add_edge(START, "main_llm")
    graph.add_conditional_edges("main_llm", should_continue)
    graph.add_edge("tool_node", "main_llm")
    graph.add_edge("memory_update", END)

    app = graph.compile(checkpointer=checkpointer)

    # -------- Run loop --------
    user_input = input("Enter your username.... ")
    cfg = {"configurable": {"thread_id": user_input}}
    print("\n", "Lets initiate your session so you can resume or start conversing...")

    # Initialize state with empty profile/summary (persisted by checkpointer)
    # You can seed profile with known facts per user/thread id.
    while True:
        user_input = input("Enter... ")
        if user_input.strip().lower() == "exit":
            break

        s = app.invoke(
            {
                "messages": [HumanMessage(content=user_input)],
                "profile": {},                # persists via checkpointer
                "summary": "",                # persists via checkpointer
                "username": user_input or "", # optional
            },
            config=cfg,
        )
        print([i.content for i in s["messages"][-3:]])

if __name__ == "__main__":
    main()
