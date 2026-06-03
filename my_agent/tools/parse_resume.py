import io
import json
import base64

import pdfplumber
from google.adk.tools import ToolContext
from vertexai.generative_models import GenerativeModel


def parse_resume(raw_text: str, source_format: str = "text", tool_context: ToolContext = None) -> dict:
    """
    Parse a resume into structured JSON with sections for education, experience,
    projects, and skills. Each item (bullet, experience, project, education entry)
    gets a unique ID so it can be referenced later when rewriting bullets.
    Call this tool whenever the user provides resume content to analyze.

    Args:
        raw_text: The resume as plain text. If source_format is 'pdf', pass
                  the file contents as a base64-encoded string instead.
        source_format: 'text' for plain text input, 'pdf' for base64-encoded PDF.

    Returns:
        A dict with two keys:
          - resume_json: structured resume data (personal_info, education,
            experience, projects, skills, additional), or null on failure.
          - parse_warnings: list of warning strings if any fields couldn't be parsed.
          -Return ONLY the resume data JSON directly, no wrapper keys like 'resume_json'.

    Expected resume_json shape:
        {
          "personal_info": {"name", "email", "phone", "location", "links": {"linkedin", "github"}},
          "education":   [{"id", "school", "degree", "major", "gpa", "start_date", "end_date"}],
          "experience":  [{"id", "company", "role", "location", "start_date", "end_date",
                           "bullets": [{"id", "content"}]}],
          "projects":    [{"id", "name", "tech_stack": [], "start_date", "end_date",
                           "bullets": [{"id", "content"}]}],
          "skills":      {"languages": [], "frameworks": [], "tools": [], "other": []},
          "additional":  {"certifications": [], "awards": []}
        }
    """
    if source_format == 'pdf':
        try:
            pdf_bytes = base64.b64decode(raw_text)
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                raw_text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
        except Exception as e:
            return {
                "resume_json": None,
                "parse_warnings": [f"Failed to parse PDF: {str(e)}"]
            }
    
    model = GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(f"""Extract the resume below into structured JSON.

Rules:
- Return ONLY valid JSON, no markdown, no wrapper keys
- Top-level keys must be EXACTLY: personal_info, education, experience, projects, skills, additional
- Use the EXACT field names below. Do NOT use synonyms (e.g. NOT "title"/"institution"/"item"/"technologies").
- Assign a short unique ID (e.g. "e1", "b2") to every experience, project, education entry, and bullet
- Missing fields use null

Exact schema (use these keys verbatim):
- personal_info: {{ "name", "email", "phone", "location", "links": {{ "linkedin", "github" }} }}
- education[]: {{ "id", "school", "degree", "major", "gpa", "start_date", "end_date", "details": [string, ...] }}
    ("school" NOT "institution"; coursework goes in "details" as a list of strings)
- experience[]: {{ "id", "company", "role", "location", "start_date", "end_date", "bullets": [{{ "id", "content" }}] }}
- projects[]: {{ "id", "name", "tech_stack": [string, ...], "start_date", "end_date", "bullets": [{{ "id", "content" }}] }}
    ("name" NOT "title"; "tech_stack" is a LIST not a string)
- Every bullet object MUST use the key "content" (NOT "item"/"text"/"description")
- Dates use YYYY-MM format
- skills: {{ "languages": [], "frameworks": [], "tools": [], "other": [] }}
- additional: {{ "certifications": [], "awards": [] }}

Resume:
{raw_text}""")
    text = response.text.strip()

    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        resume_json = json.loads(text)
        # Store the parsed resume in session state as the single source of truth.
        # Downstream tools (analyze, check, render, save) read it from here instead
        # of receiving it as a parameter, so the large JSON never enters a function call.
        if tool_context is not None:
            tool_context.state["resume_json"] = resume_json
        return {"resume_json": resume_json, "parse_warnings": []}
    except json.JSONDecodeError as e:
        return {
            "resume_json": None,
            "parse_warnings": [f"Failed to parse JSON from model response: {e}"],
        }
