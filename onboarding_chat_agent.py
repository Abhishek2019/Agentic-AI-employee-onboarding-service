from typing import TypedDict, Annotated, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph.message import add_messages 
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_core.tools import tool

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
import os

from langgraph.checkpoint.postgres import PostgresSaver
import psycopg


#------------------------ New Function
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


load_dotenv(override=True)


def main():

    # @tool
    # def test_tool(a:int, b:int)->float:
    #     '''perform linux operation on 2 integers and return the result'''
    #     return (a**2 + b**2)

    POOL: ConnectionPool = ConnectionPool(
        conninfo=os.getenv("DATABASE_URL"),
        min_size=1,
        max_size=5,
        kwargs={"row_factory": dict_row},
    )

    @tool
    def assign_seating_space(seat_type: Optional[str] = None) -> dict:
        """
        Assign me a available seat to employee as if optional seating type (seat_id, seat_type) or a message if none found.
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
        base_url = os.getenv("JETSTREAM_BASE_URL"),
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("JETSTREAM_MODEL"),
        temperature=0.2,
    )

    # llm_bind = create_agent(llm, tools)
    llm_bind = llm.bind_tools(tools)

    # math_response = llm_bind.invoke(
    # [HumanMessage(content="assign me a seat")]
    # )

    # print(math_response)



    class State(TypedDict):
        messages: Annotated[list[BaseMessage],add_messages]
        username: str


    def process(s:State)->State:
        #print("initial message ", s["messages"])
        response = llm_bind.invoke(s["messages"][-1:])
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
    graph.add_node("tool_node", ToolNode(tools))

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

        print( [i.content for i in s["messages"][-3:]])



if __name__ == "__main__":

    main()





# TRUNCATE TABLE checkpoint_writes, checkpoint_blobs, checkpoints;

# -- If you get FK constraint errors, do it in order:
# DELETE FROM checkpoint_writes;
# DELETE FROM checkpoint_blobs;
# DELETE FROM checkpoints;