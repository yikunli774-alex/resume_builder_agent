# Resume Builder Agent

An AI resume-tailoring agent for SWE internship candidates. Paste your resume and a target job description; the agent scores the match, interviews you for hidden achievements, rewrites bullets against a quality rubric, renders a polished PDF, and saves named versions to MongoDB — one per company and role.

Built for the Google Cloud Rapid Agent Hackathon (MongoDB track) with the Google Agent Development Kit (ADK) and Gemini.

**The agent suggests; the user decides.** Every change is applied only after explicit approval, and truthfulness is enforced over impressiveness — the agent asks follow-up questions instead of inventing metrics, tools, or experience.

## How it works

```
┌─────────────────────────── Streamlit UI ───────────────────────────┐
│  chat + live tool progress          │  rendered resume preview     │
└───────────────┬─────────────────────────────────────▲──────────────┘
                ▼                                     │ html_preview
        ADK Runner ── root_agent (gemini-2.5-pro, orchestrator)
                │  decides which tool to call; never sees the full resume
                ▼
   10 tools (each may run its own Gemini call internally)
                │
        session state["resume_json"]  ←— single source of truth
                │
     MongoDB Atlas (versions)   ·   Jinja2 + Playwright (PDF)
```

The conversation follows five phases: **intake** (parse + JD match score) → **clarification loop** (probe for quantifiable achievements) → **apply** (user-approved edits) → **refinement** → **save** (versioned to MongoDB, rendered to PDF).

### Tools

| Tool | What it does |
|---|---|
| `parse_resume` | Plain text → structured JSON (schema-normalized), stored in session state |
| `analyze_jd_match` | Keyword coverage score + ranked, schema-constrained suggestions |
| `rewrite_bullet` | Generator–validator loop: Gemini rewrite, code-checked against a rubric (action verbs, quantification, no weak phrases), up to 3 self-correcting retries |
| `edit_resume` | Unified path-based editor: set fields, add/remove list items, add/remove whole entries, add/remove bullets, reorder entries |
| `check_formatting` | Deterministic rule checks (dates, bullet counts, required fields) |
| `render_template` | Jinja2 HTML preview / Playwright PDF (Jake's Resume style) |
| `save_resume_version` / `list_resume_versions` / `load_resume_version` | Named version snapshots in MongoDB Atlas — one per company/role; any version can be reloaded as the working draft or downloaded as a PDF straight from the history panel |
| `compare_versions` | Structured diff between two saved versions |

### Design decisions that mattered

- **The resume lives in ADK session state, never in function-call arguments.** Passing `resume_json` through the model caused `MALFORMED_FUNCTION_CALL` crashes, schema drift, and a snowballing context. Tools read and write state directly; the orchestrator only passes small arguments (`jd_text`, `bullet_id`, `label`).
- **Big or deterministic data never goes through the LLM.** PDFs are text-extracted locally with pdfplumber before anything reaches the agent; version history is fetched by the frontend calling the tool function directly.
- **LLM decides, code executes.** Suggestion ordering, rubric validation, schema normalization, and path whitelisting are deterministic code — the model is only trusted with judgment, not bookkeeping.
- **The tool surface matches the prompt's promises.** Every action the instruction offers is backed by a real tool; structural edits go through whitelisted paths so the model cannot write outside the schema.

More war stories (and the bugs behind these rules) are in [DEVLOG_EN.md](DEVLOG_EN.md) ([中文原版](DEVLOG_CN.md)).

## Quickstart

Prerequisites: Python 3.10+, a Google Cloud project with Vertex AI enabled (`gcloud auth application-default login`), and a MongoDB Atlas cluster.

```bash
pip install -r requirements.txt
python -m playwright install chromium   # browser binary for PDF rendering

# my_agent/.env
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=<your-project-id>
GOOGLE_CLOUD_LOCATION=<region>
MONGO_URI=<your-atlas-connection-string>
MONGO_DB=<database-name>

python -m streamlit run frontend/app.py
```

Open http://localhost:8501, upload a resume PDF (or paste text), then paste a job description.

> Note: a `Cloud Resource Manager API ... 403` traceback at startup is harmless — the SDK falls back to the project id from `.env`. Edits under `my_agent/` require a server restart (Streamlit only hot-reloads `frontend/app.py`).

## Status & roadmap

Runs locally end-to-end (single user). Before a public deployment (Cloud Run is the planned target) the remaining checklist is: per-user version isolation (the `user_session` field exists in the schema; the wiring is pending), a self-serve clear-history button, secrets via Secret Manager instead of `.env`, an Atlas IP allowlist, and Playwright/chromium baked into the container image.

## Project structure

```
my_agent/
  agent.py               # root_agent: orchestrator instruction + tool registry
  tools/                 # the 10 tools (each docstring doubles as Gemini's tool manual)
config/
  rubric.yaml            # bullet quality rubric for rewrite_bullet
  structure_rules.yaml   # formatting rules for check_formatting
  templates/jakes_resume_en/   # Jinja2 HTML template + CSS
frontend/
  app.py                 # Streamlit UI: chat, live tool progress, preview, versions
DEVLOG_EN.md             # engineering log: decisions, pitfalls, lessons (中文: DEVLOG_CN.md)
```
