# Project Memo: Resume Agent (Google Cloud × Gemini Hackathon)

## Overview

A Resume Agent that lets users upload their resume, select a target template,
and have an AI agent reformat and tailor it. Every output version is saved to
MongoDB with a user-defined label (e.g. "Google SWE Intern 2026") so users
can manage multiple resume versions over time.

**Hackathon:** Google Cloud Rapid Agent Hackathon (Devpost)
**Deadline:** June 11, 2026, 2:00 PM PDT
**Track:** MongoDB Partner Track
**Prize:** $5K / $3K / $2K (1st–3rd in track)

---

## Tech Stack

| Layer | Choice |
|---|---|
| Agent core | Google ADK (Python), Gemini 2.5 Flash via Vertex AI |
| Database | MongoDB Atlas (free tier) |
| DB integration | MongoDB MCP Server |
| PDF parsing | `pdfplumber` |
| Template rendering | `jinja2` → HTML → PDF via `weasyprint` |
| Frontend | Streamlit |
| Deployment | Local for demo; optionally Cloud Run |
| GCP auth | `gcloud auth application-default login` (already set up) |
| GCP project | Already configured |

---

## Core Features (Must-Have)

1. **Upload resume** — PDF or paste plain text
2. **Parse resume** — Agent extracts structured fields: education, experience, projects, skills, summary
3. **Select template** — User picks from 2–3 templates (Jake's Resume style, clean single-column, technical two-column)
4. **Generate output** — Agent injects parsed content into template, outputs formatted PDF
5. **Save to MongoDB** — Each output is saved with: user label, date, original content, formatted content, template used
6. **Version history** — List and download any past version
7. **Version diff** — Compare two versions: which bullets changed, which sections changed

## Stretch Features (If Time Allows)

8. Content suggestions — flag weak bullets, missing keywords
9. Multi-template preview — side-by-side before choosing
10. JD-based tailoring — paste a job description, agent suggests edits

---

## Agent Flow (Core Loop)

```
User uploads resume (PDF or text)
        ↓
[Tool: parse_resume] → structured JSON (education, experience, projects, skills)
        ↓
User selects template
        ↓
[Tool: render_template] → HTML string using jinja2
        ↓
[Tool: html_to_pdf] → PDF bytes
        ↓
User adds label ("Google SWE Intern 2026")
        ↓
[Tool: save_to_mongodb] → stored with metadata
        ↓
Return download link + confirmation
```

---

## MongoDB Schema

**Collection: `resume_versions`**

```json
{
  "_id": "ObjectId",
  "user_session": "string",
  "label": "string (e.g. 'Google SWE Intern 2026')",
  "created_at": "ISODate",
  "template_used": "string",
  "parsed_content": {
    "name": "string",
    "contact": "object",
    "education": ["..."],
    "experience": ["..."],
    "projects": ["..."],
    "skills": ["..."]
  },
  "output_pdf_base64": "string"
}
```

---

## Project Structure (Proposed)

```
resume-agent/
├── agent/
│   ├── __init__.py
│   ├── agent.py          # ADK root agent definition
│   └── tools.py          # parse_resume, render_template, html_to_pdf, save_to_mongodb
├── templates/
│   ├── jakes.html        # Jake's Resume style
│   ├── clean.html        # Simple single-column
│   └── technical.html    # Two-column technical
├── frontend/
│   └── app.py            # Streamlit UI
├── db/
│   └── mongo_client.py   # MongoDB Atlas connection
├── requirements.txt
└── .env                  # MONGO_URI, GCP project vars (not committed)
```

---

## Environment / Auth Notes

- GCP auth: `gcloud auth application-default login` already done
- ADK backend: Vertex AI (not Google AI Studio — no API key needed)
- MongoDB: need `MONGO_URI` from Atlas free cluster (create at mongodb.com)
- MongoDB MCP Server: needed for ADK ↔ MongoDB integration

---

## What Claude Code Should Handle

- Scaffolding the full project structure above
- `tools.py` — all four tool functions
- `agent.py` — ADK agent definition wiring tools together
- Jinja2 HTML templates (all 3)
- `mongo_client.py` — Atlas connection + insert/query helpers
- `app.py` — Streamlit UI (upload, template selector, history view, download)
- `requirements.txt`
- End-to-end testing of the parse → render → save pipeline

## What Requires Human Judgment

- MongoDB Atlas cluster setup (GUI, needs account)
- GCP project / Vertex AI quota confirmation
- Template aesthetic decisions (how the final PDF looks)
- Choosing which resume to use as the test input
- Recording the demo video

---

## Current Status

- [x] ADK installed, `my_agent` created with Vertex AI backend
- [x] GCP project set, `gcloud auth application-default login` done
- [ ] MongoDB Atlas cluster not yet created
- [ ] No code written yet
- [ ] Templates not yet designed

---

## Submission Requirements

- Hosted project link (or video demo)
- Open-source GitHub repo with license
- ~3 min demo video
- Devpost submission form completed
- Must integrate MongoDB MCP Server meaningfully
