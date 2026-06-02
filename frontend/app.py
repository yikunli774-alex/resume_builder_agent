"""
Resume Agent — Streamlit frontend

Layout:
  Left column  — chat with the agent
  Right column — live resume HTML preview + download button

Java analogy:
  st.session_state  ≈  HttpSession   (persists across re-renders)
  Runner            ≈  embedded Spring Boot server (handles agent loop)
  Each re-render    ≈  a new HTTP request hitting the same session
"""

import asyncio
import base64
import os
import sys
import uuid
from pathlib import Path

import streamlit as st

# Make sure the project root is on the path so `my_agent` is importable
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / "my_agent" / ".env")

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types

import my_agent.agent as agent_module

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Resume Agent",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.title("📄 Resume Agent")
st.caption("Upload your resume, paste a JD, and let the agent tailor it for you.")

# ── Session state bootstrap ───────────────────────────────────────────────────
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "runner" not in st.session_state:
    session_service = InMemorySessionService()
    st.session_state.runner = Runner(
        agent=agent_module.root_agent,
        app_name="resume_agent",
        session_service=session_service,
    )
    # Pre-create the ADK session for this user
    asyncio.run(
        session_service.create_session(
            app_name="resume_agent",
            user_id="user",
            session_id=st.session_state.session_id,
        )
    )

if "messages" not in st.session_state:
    st.session_state.messages = []   # [{role, content}]

if "html_preview" not in st.session_state:
    st.session_state.html_preview = None

if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = None


# ── Helper: send a message to the agent and collect the reply ─────────────────
def chat(user_text: str) -> str:
    """Send user_text to the ADK runner, return the agent's final text reply."""
    runner: Runner = st.session_state.runner
    content = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_text)],
    )
    reply_parts = []
    for event in runner.run(
        user_id="user",
        session_id=st.session_state.session_id,
        new_message=content,
    ):
        # Capture tool output side-effects for preview updates
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    reply_parts.append(part.text)
                # If a tool returned html_preview, capture it
                if hasattr(part, "function_response"):
                    resp = part.function_response.response or {}
                    if resp.get("html_preview"):
                        st.session_state.html_preview = resp["html_preview"]
                    if resp.get("file_path"):
                        st.session_state.pdf_path = resp["file_path"]

    return "".join(reply_parts).strip() or "(no text response)"


# ── Layout: two columns ───────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ── LEFT: upload panel + chat ────────────────────────────────────────────────
with left:
    st.subheader("Chat")

    # File upload — sends PDF content to agent as a first message
    uploaded = st.file_uploader("Upload resume (PDF)", type=["pdf"], key="uploader")
    if uploaded and not st.session_state.get("resume_uploaded"):
        pdf_b64 = base64.b64encode(uploaded.read()).decode()
        intro = (
            f"I've uploaded my resume (PDF). Here it is as base64:\n{pdf_b64}\n\n"
            "Please parse it using the parse_resume tool with source_format='pdf'."
        )
        with st.spinner("Parsing resume…"):
            reply = chat(intro)
        st.session_state.messages.append({"role": "user", "content": "📎 Resume uploaded"})
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.session_state.resume_uploaded = True
        st.rerun()

    # JD input
    jd_text = st.text_area("Paste job description (optional)", height=120, key="jd_input")
    if st.button("Analyze JD match") and jd_text.strip():
        msg = f"Here is the job description I want to target:\n\n{jd_text}\n\nPlease analyze how well my resume matches it."
        with st.spinner("Analyzing…"):
            reply = chat(msg)
        st.session_state.messages.append({"role": "user", "content": "JD submitted for analysis"})
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

    st.divider()

    # Conversation history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Talk to the agent…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                reply = chat(prompt)
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

# ── RIGHT: resume preview + download ─────────────────────────────────────────
with right:
    st.subheader("Resume Preview")

    if st.session_state.html_preview:
        st.components.v1.html(st.session_state.html_preview, height=900, scrolling=True)

        # Download PDF if available
        if st.session_state.pdf_path and Path(st.session_state.pdf_path).exists():
            with open(st.session_state.pdf_path, "rb") as f:
                st.download_button(
                    label="⬇ Download PDF",
                    data=f.read(),
                    file_name="resume.pdf",
                    mime="application/pdf",
                )

        if st.button("Render / refresh PDF"):
            with st.spinner("Rendering…"):
                reply = chat("Please render my current resume draft as a PDF using the jakes_resume_en template.")
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()
    else:
        st.info("The resume preview will appear here once you upload a resume and the agent parses it.")

    st.divider()
    st.subheader("Version History")
    if st.button("Refresh history"):
        with st.spinner("Loading…"):
            reply = chat("List all my saved resume versions.")
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()
