from typing import TypedDict, Annotated
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages 
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

import os, threading, asyncio
from typing import Any, List
from dotenv import load_dotenv
from concurrent.futures import Future
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools


from fastmcp import Client


from langgraph.checkpoint.postgres import PostgresSaver
import psycopg

load_dotenv(override=True)

@tool
def test_tool(a:int, b:int)->float:
    '''perform linux operation on 2 integers and return the result'''
    return (a**2 + b**2)


class _BackgroundLoop:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.t = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.t.start()

    def run(self, coro) -> Any:
        fut: Future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return fut.result()  # blocks until done

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.t.join()

# class MCPClientSync:
#     def __init__(self, servers: dict[str, dict]):
#         self._loop = _BackgroundLoop()
#         self._client = MultiServerMCPClient(servers)

#     def get_tool_specs(self):
#         return self._loop.run(self._client.get_tools())

#     def load_langchain_tools(self, server_name: str):
#         async def _load():
#             async with self._client.session(server_name) as session:
#                 return await load_mcp_tools(session)
#         return self._loop.run(_load())

#     def close(self):
#         self._loop.stop()

class MCPClientSync:
    def __init__(self, servers: dict[str, dict]):
        self._loop = _BackgroundLoop()
        self._client = MultiServerMCPClient(servers)
        self._sessions = {}     # server_name -> session
        self._lc_tools = {}     # server_name -> list[BaseTool]

    def start_server_session(self, server_name: str):
        async def _start():
            session = await self._client.session(server_name).__aenter__()
            tools = await load_mcp_tools(session)   # tools bound to this live session
            return session, tools
        session, tools = self._loop.run(_start())
        self._sessions[server_name] = session
        self._lc_tools[server_name] = tools
        return tools

    def get_lc_tools(self, server_name: str):
        return self._lc_tools[server_name]

    def close(self):
        async def _close():
            # Close sessions first
            for s in list(self._sessions.values()):
                try:
                    await s.__aexit__(None, None, None)
                except Exception:
                    pass
            self._sessions.clear()
            # Close client
            await self._client.aclose()
        try:
            self._loop.run(_close())
        finally:
            self._loop.stop()




servers = {
    "assign_seating_space": {
        "url": os.getenv("MCP_HTTP_URL"),
        "transport": "streamable_http",
    }
}

mcp_sync = MCPClientSync(servers)
lc_tools = mcp_sync.start_server_session("assign_seating_space")

lc_tools.append(test_tool)
# print(specs)
print(lc_tools)



DSN = os.getenv("DATABASE_URL")
conn = psycopg.connect(DSN)
conn.autocommit = True
checkpointer = PostgresSaver(conn)
checkpointer.setup()


llm = model = ChatOpenAI(
    base_url = os.getenv("JETSTREAM_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    model=os.getenv("JETSTREAM_MODEL"),
    temperature=0.2,
)


llm_bind = llm.bind_tools(lc_tools)



class State(TypedDict):
    messages: Annotated[list[BaseMessage],add_messages]
    username: str


def process(s:State)->State:
    response = llm_bind.invoke(s["messages"])
    return {"messages": [response if isinstance(response, AIMessage) else AIMessage(content=response.content)]}


def should_continue(state: State):
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"

    # Otherwise, we stop (reply to the user)
    return END

graph = StateGraph(State)

graph.add_node("main_llm", process)
graph.add_node("tool_node", ToolNode(lc_tools))

graph.add_edge(START, "main_llm")
graph.add_conditional_edges("main_llm", should_continue )
graph.add_edge("tool_node", "main_llm")

app = graph.compile(checkpointer=checkpointer)



user_input = input("Enter your username.... ")
cfg = {"configurable": {"thread_id": user_input}}
print("\n","Lets initiate your session so you can resume or strat conversing...")

while True:

    user_input = input("Enter... ")

    if user_input.strip().lower() == "exit":
        break

    s = app.invoke({"messages":[HumanMessage(content = user_input)]}, config=cfg)

    print( s["messages"][-1])


mcp_sync.close()


