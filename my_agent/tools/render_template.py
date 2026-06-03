import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "config" / "templates"

# Worker script run in a separate process. Playwright's sync API refuses to run
# inside an asyncio event loop (e.g. under `adk web`), so we render the PDF in a
# clean subprocess that has no running loop. Usage: python -c <this> <html_file> <out_pdf>
_PDF_WORKER = """
import sys
from playwright.sync_api import sync_playwright

html_file, out_pdf = sys.argv[1], sys.argv[2]
with open(html_file, encoding="utf-8") as f:
    html = f.read()
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.set_content(html)
    page.pdf(
        path=out_pdf,
        format="Letter",
        margin={"top": "0.5in", "bottom": "0.5in", "left": "0.5in", "right": "0.5in"},
    )
    browser.close()
"""


def _html_to_pdf(html: str, output_path: str) -> None:
    """Render HTML to a PDF file in a separate process (avoids asyncio-loop conflict)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        html_file = tmp.name
    try:
        subprocess.run(
            [sys.executable, "-c", _PDF_WORKER, html_file, output_path],
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        Path(html_file).unlink(missing_ok=True)


def render_template(
    resume_json: dict,
    template_name: str = "jakes_resume_en",
    output_format: str = "pdf",
) -> dict:
    """
    Render a resume into a formatted PDF or HTML preview using a named template.
    Call this when the user wants to generate a formatted resume file for download,
    or when you want to show them an HTML preview.

    Args:
        resume_json: Structured resume data — the output from parse_resume.
        template_name: Which template to use. Currently available: 'jakes_resume_en'.
        output_format: 'pdf' to generate a downloadable PDF file, or 'html' for
                       an inline HTML preview only.

    Returns:
        A dict with:
          - file_path: absolute path to the generated PDF (None for html-only output).
          - html_preview: the rendered HTML string (always included).
          - error: present only if rendering failed (e.g. template not found).

    Behavior:
        1. Check that TEMPLATES_DIR / template_name exists. If not, return an error dict.
        2. Use Jinja2 FileSystemLoader pointed at the template directory.
        3. Load 'template.html' and render it with resume=resume_json.
        4. If output_format == 'html', return immediately with just html_preview.
        5. For 'pdf': use Playwright (sync API) to open a new browser page,
           set_content(html), call page.pdf() with Letter format, save to /tmp/.
        6. Return file_path and html_preview.

    Note: Use a random UUID (8 hex chars) in the output filename to avoid collisions.
    """
    if not (TEMPLATES_DIR / template_name).exists():
        return {"error": f"Template '{template_name}' not found."}
    
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR / template_name))
    template = env.get_template("template.html")
    html_preview = template.render(resume=resume_json)
    if output_format == "html":
        return {"file_path": None, "html_preview": html_preview}
    
    output_path = f"/tmp/resume_{uuid.uuid4().hex[:8]}.pdf"
    try:
        _html_to_pdf(html_preview, output_path)
    except subprocess.CalledProcessError as e:
        return {
            "file_path": None,
            "html_preview": html_preview,
            "error": f"PDF rendering failed: {e.stderr or e}",
        }

    return {"file_path": output_path, "html_preview": html_preview}
