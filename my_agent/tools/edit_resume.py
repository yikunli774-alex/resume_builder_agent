import re

from google.adk.tools import ToolContext

# Every field/list the template renders, by section and shape. Bullets are
# intentionally excluded — bullet prose is edited with rewrite_bullet (it has
# rubric validation). Validating against this map keeps Gemini from writing keys
# outside the schema (e.g. a "summary" the template cannot render).
_PERSONAL = {"name", "email", "phone", "location"}
_PERSONAL_LINKS = {"linkedin", "github"}
_ENTRY_FIELDS = {
    "education":  {"school": "scalar", "degree": "scalar", "major": "scalar",
                   "gpa": "scalar", "start_date": "scalar", "end_date": "scalar",
                   "details": "list"},
    "experience": {"company": "scalar", "role": "scalar", "location": "scalar",
                   "start_date": "scalar", "end_date": "scalar"},
    "projects":   {"name": "scalar", "start_date": "scalar", "end_date": "scalar",
                   "tech_stack": "list"},
}
_FIXED_LISTS = {
    "skills":     {"languages", "frameworks", "tools", "other"},
    "additional": {"certifications", "awards"},
}

_SEG = re.compile(r"^([a-zA-Z_]+)(?:\[([^\]]+)\])?$")


def _ensure_dict(parent: dict, key: str) -> dict:
    """Return parent[key] as a dict, creating/repairing it (parse leaves nulls)."""
    value = parent.get(key)
    if not isinstance(value, dict):
        value = {}
        parent[key] = value
    return value


def _find_entry(entries: list, idx: str):
    """Locate a list entry by its id, or by 0-based numeric index as a fallback."""
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get("id")) == str(idx):
            return entry
    if str(idx).isdigit() and 0 <= int(idx) < len(entries):
        return entries[int(idx)]
    return None


def _resolve(resume: dict, path: str):
    """Map a dotted path to (holder_dict, final_key, shape) or an error string.

    Supported paths:
      personal_info.<field> / personal_info.links.<linkedin|github>
      skills.<languages|frameworks|tools|other>
      additional.<certifications|awards>
      <education|experience|projects>[<id>].<field>
    """
    parts = path.split(".")
    head = _SEG.match(parts[0])
    if not head:
        return None, None, None, f"Bad path segment: '{parts[0]}'"
    section, idx = head.group(1), head.group(2)

    if section == "personal_info":
        if len(parts) == 2 and parts[1] in _PERSONAL:
            return _ensure_dict(resume, "personal_info"), parts[1], "scalar", None
        if len(parts) == 3 and parts[1] == "links" and parts[2] in _PERSONAL_LINKS:
            links = _ensure_dict(_ensure_dict(resume, "personal_info"), "links")
            return links, parts[2], "scalar", None
        return None, None, None, f"'{path}' is not an editable personal_info field"

    if section in _FIXED_LISTS:
        if len(parts) == 2 and parts[1] in _FIXED_LISTS[section]:
            return _ensure_dict(resume, section), parts[1], "list", None
        return None, None, None, (
            f"'{path}' is not an editable {section} field "
            f"(allowed: {sorted(_FIXED_LISTS[section])})")

    if section in _ENTRY_FIELDS:
        if idx is None or len(parts) != 2:
            return None, None, None, (
                f"Use {section}[id].field, e.g. {section}[<id>].start_date")
        entries = resume.get(section) or []
        entry = _find_entry(entries, idx)
        if entry is None:
            valid = [e.get("id") for e in entries if isinstance(e, dict)]
            return None, None, None, (
                f"No {section} entry with id '{idx}'. Valid ids: {valid}")
        shape = _ENTRY_FIELDS[section].get(parts[1])
        if shape is None:
            return None, None, None, (
                f"'{parts[1]}' is not editable on {section} "
                f"(allowed: {sorted(_ENTRY_FIELDS[section])}). "
                f"For bullet text use rewrite_bullet.")
        return entry, parts[1], shape, None

    return None, None, None, (
        f"Unknown section '{section}'. Editable sections: personal_info, skills, "
        f"additional, education, experience, projects.")


def edit_resume(path: str, value: str = None, operation: str = "set",
                tool_context: ToolContext = None) -> dict:
    """
    Edit any single field or list item the resume shows, in one call. Use this to
    add or change contact info, skills, coursework, project tech stack, dates,
    certifications, awards, or any education/experience/project field — anything
    EXCEPT bullet prose (rewrite bullets with rewrite_bullet).

    Address the target with a dotted path; operate with set / add / remove:
      - set    a single value:   edit_resume("personal_info.links.github", "github.com/me", "set")
      - set    an entry field:   edit_resume("experience[e1].end_date", "2025-08", "set")
      - add    a list item:      edit_resume("skills.tools", "Docker", "add")
      - add    coursework:       edit_resume("education[ed1].details", "Operating Systems", "add")
      - remove a list item:      edit_resume("skills.other", "Software Engineering", "remove")

    Valid paths:
      personal_info.{name|email|phone|location}, personal_info.links.{linkedin|github},
      skills.{languages|frameworks|tools|other}, additional.{certifications|awards},
      education[id].{school|degree|major|gpa|start_date|end_date|details},
      experience[id].{company|role|location|start_date|end_date},
      projects[id].{name|start_date|end_date|tech_stack}.
    Entry ids come from the parsed resume; if you use a wrong id the tool returns
    the valid ids. Use only the user's real values — never invent one.

    Args:
        path: Dotted path to the field or list (see above).
        value: The value to set, add, or remove.
        operation: "set" for single fields, "add"/"remove" for list items.

    Returns:
        A dict describing the change, or an error explaining what was wrong.
    """
    resume = tool_context.state.get("resume_json") if tool_context else None
    if not resume:
        return {"error": "No resume found in session. Please parse a resume first."}

    operation = (operation or "set").lower()
    if operation not in ("set", "add", "remove"):
        return {"error": f"operation must be set, add, or remove (got '{operation}')."}
    if value is None:
        return {"error": f"'{operation}' requires a value."}

    holder, key, shape, err = _resolve(resume, path)
    if err:
        return {"error": err}

    if operation == "set":
        if shape != "list":
            holder[key] = value
        else:
            return {"error": f"'{path}' is a list; use add or remove, not set."}
    else:
        if shape != "list":
            return {"error": f"'{path}' is a single value; use set, not {operation}."}
        items = holder.get(key)
        if not isinstance(items, list):
            items = []
            holder[key] = items
        if operation == "add":
            if value not in items:
                items.append(value)
        else:
            holder[key] = [x for x in items if x != value]

    # Reassign the top-level key so ADK's delta-aware state records the change.
    tool_context.state["resume_json"] = resume
    return {"updated": True, "path": path, "operation": operation,
            "value": value, "current": holder.get(key)}
