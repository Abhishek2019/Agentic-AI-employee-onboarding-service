import os
import time
import requests
import streamlit as st
from typing import TypedDict, Annotated
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import event, text
from dotenv import load_dotenv
import asyncio

load_dotenv()

from employee import Employee

@st.cache_resource
def get_async_engine():
    dsn = os.getenv("DATABASE_URL")
    engine = create_async_engine(
        dsn,
        pool_size=10,
        max_overflow=5,
        pool_pre_ping=True,
        pool_recycle=1800,
        isolation_level="READ COMMITTED",
        future=True,
    )

    # set search_path on each new DBAPI conn (note: use .sync_engine for async)
    # @event.listens_for(engine.sync_engine, "connect")
    # def _set_search_path(dbapi_conn, conn_record):
    #     cur = dbapi_conn.cursor()
    #     cur.execute("SET search_path TO onboarding, public")
    #     cur.close()

    return engine

@st.cache_resource
def get_async_sessionmaker():
    return async_sessionmaker(bind=get_async_engine(), expire_on_commit=False)


# one object per session
if "employee" not in st.session_state:
    st.session_state.employee = Employee()




# -------------------------------
# Page / Layout
# --------------------------------

st.set_page_config(page_title="Agentic Onboarding Chat", layout="centered")
st.title("New Employee Onboarding — ChatBot")
st.caption("Type below to chat.")


# -------------------------------
# Session State for Messages
# -------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []

# Seed first assistant message
if len(st.session_state.messages) == 0:
    st.session_state.messages.append({"role": "assistant", "content": "Hi! I can help with onboarding. What is your name?"})

# -------------------------------
# Backend reply function (single entry point)
# -------------------------------

def backend_reply(user_text: str, history: list[str]) -> str:
    """
    Central place to compute the assistant's reply.
    Replace this with a real model or API later.

    Args:
        user_text: the latest user message
        history: list of past messages (as dicts with role/content)

    Returns:
        assistant reply (str)
    """

    # Local simple logic (placeholder):
    text = user_text.strip().lower()

    st.session_state.employee.seat_type = "cabin"

    from llm_tools import assign_seating_space
    out = asyncio.run(assign_seating_space(get_async_sessionmaker(), st.session_state.employee.seat_type))
    print(out, type(out))

    print(out)
    print(type(out))
    # Default echo with slight delay to mimic thinking
    time.sleep(0.2)
    return "Your input text is: "+text

# -------------------------------
# Render previous history
# -------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# -------------------------------
# Input box
# -------------------------------

user_input = st.chat_input("Type your message…")

if user_input:
    # Append user msg
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Get assistant reply from backend function
    reply = backend_reply(user_input, st.session_state.messages)

    # Append and display assistant msg
    st.session_state.messages.append({"role": "assistant", "content": reply})
    with st.chat_message("assistant"):
        st.markdown(reply)
