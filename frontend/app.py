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
import io
import os
import sys
import uuid
from pathlib import Path

import pdfplumber
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

# Compact header bar — keeps the working area tight instead of a big centered title
st.markdown(
    "<div style='display:flex;align-items:baseline;gap:10px;margin:-8px 0 6px;'>"
    "<span style='font-size:19px;font-weight:600;'>📄 Resume Agent</span>"
    "<span style='color:#888;font-size:13px;'>paste your resume, then a JD, into the chat — the agent tailors it</span>"
    "</div>",
    unsafe_allow_html=True,
)

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
                # If a tool returned html_preview, capture it. NOTE: a Part always
                # HAS a `function_response` attribute (it is just None for text /
                # function_call parts), so check the value, not just the attribute.
                if getattr(part, "function_response", None) is not None:
                    resp = part.function_response.response or {}
                    if resp.get("html_preview"):
                        st.session_state.html_preview = resp["html_preview"]
                    if resp.get("file_path"):
                        st.session_state.pdf_path = resp["file_path"]

    return "".join(reply_parts).strip() or "(no text response)"


# ── Layout: two columns ───────────────────────────────────────────────────────
left, right = st.columns([1, 1], gap="medium")

# ── LEFT: chat ────────────────────────────────────────────────────────────────
with left:
    # Resume PDF upload tucked into an expander to keep the chat area clean.
    # We extract the text locally with pdfplumber and send only that text to the
    # agent — raw PDF bytes never go through the LLM (that path hangs).
    with st.expander("📎 Upload resume PDF (optional)", expanded=False):
        uploaded = st.file_uploader(
            "PDF", type=["pdf"], key="uploader", label_visibility="collapsed"
        )
        if uploaded and not st.session_state.get("resume_uploaded"):
            with pdfplumber.open(io.BytesIO(uploaded.read())) as pdf:
                resume_text = "\n".join(
                    page.extract_text() for page in pdf.pages if page.extract_text()
                )
            intro = (
                f"Here is my resume:\n\n{resume_text}\n\n"
                "Please parse it with the parse_resume tool."
            )
            with st.spinner("Parsing resume…"):
                reply = chat(intro)
            st.session_state.messages.append({"role": "user", "content": "📎 Resume uploaded"})
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.session_state.resume_uploaded = True
            st.rerun()

    # Fixed-height scrollable history so the chat never grows the page endlessly.
    history = st.container(height=470)
    with history:
        if not st.session_state.messages:
            st.caption("Paste or upload your resume to start, then paste the target job description.")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("Paste your resume or a JD, or talk to the agent…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.spinner("Thinking…"):
            reply = chat(prompt)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

# ── RIGHT: resume preview ─────────────────────────────────────────────────────
with right:
    if st.session_state.html_preview:
        st.components.v1.html(st.session_state.html_preview, height=620, scrolling=True)

        c1, c2 = st.columns(2)
        with c1:
            if st.session_state.pdf_path and Path(st.session_state.pdf_path).exists():
                with open(st.session_state.pdf_path, "rb") as f:
                    st.download_button(
                        "⬇ Download PDF", data=f.read(), file_name="resume.pdf",
                        mime="application/pdf", use_container_width=True,
                    )
        with c2:
            if st.button("⟳ Refresh PDF", use_container_width=True):
                with st.spinner("Rendering…"):
                    reply = chat("Please render my current resume draft as a PDF using the jakes_resume_en template.")
                st.session_state.messages.append({"role": "assistant", "content": reply})
                st.rerun()
    else:
        st.info("Preview appears here once the agent renders your resume.")

    with st.expander("🗂 Version history", expanded=False):
        if st.button("Refresh history", use_container_width=True):
            with st.spinner("Loading…"):
                reply = chat("List all my saved resume versions.")
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()
