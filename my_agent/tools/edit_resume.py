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
                   "start_date": "scalar", "end_date": "scalar",
                   "bullets": "bullets"},
    "projects":   {"name": "scalar", "start_date": "scalar", "end_date": "scalar",
                   "tech_stack": "list", "bullets": "bullets"},
}
_FIXED_LISTS = {
    "skills":     {"languages", "frameworks", "tools", "other"},
    "additional": {"certifications", "awards"},
}

# add_entry skeletons: every key the template may render, so a fresh entry
# renders cleanly before the agent fills it in with follow-up set calls.
_ENTRY_SKELETONS = {
    "education":  {"school": "", "degree": "", "major": "", "gpa": "",
                   "start_date": "", "end_date": "", "details": []},
    "experience": {"company": "", "role": "", "location": "",
                   "start_date": "", "end_date": "", "bullets": []},
    "projects":   {"name": "", "tech_stack": [],
                   "start_date": "", "end_date": "", "bullets": []},
}
_TITLE_FIELD = {"education": "school", "experience": "company", "projects": "name"}
_ID_PREFIX = {"education": "ed", "experience": "ex", "projects": "p"}

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


def _all_ids(resume: dict) -> set:
    """Every entry id and bullet id currently in the resume, as strings."""
    ids = set()
    for section in _ENTRY_FIELDS:
        for entry in resume.get(section) or []:
            if isinstance(entry, dict):
                ids.add(str(entry.get("id")))
                for bullet in entry.get("bullets") or []:
                    if isinstance(bullet, dict):
                        ids.add(str(bullet.get("id")))
    return ids


def _new_id(resume: dict, prefix: str) -> str:
    """Generate a short id (prefix + counter) that collides with nothing."""
    ids = _all_ids(resume)
    n = 1
    while f"{prefix}{n}" in ids:
        n += 1
    return f"{prefix}{n}"


def _structural(resume: dict, path: str, value, operation: str) -> dict:
    """add_entry / remove_entry / move — whole-entry operations on a section."""
    parts = path.split(".")
    head = _SEG.match(parts[0])
    if not head or len(parts) != 1:
        return {"error": f"'{operation}' addresses a section or entry, e.g. "
                         f"'projects' (add_entry) or 'projects[p3]' (remove_entry/move)."}
    section, idx = head.group(1), head.group(2)
    if section not in _ENTRY_FIELDS:
        return {"error": f"'{operation}' works on education, experience, or projects "
                         f"(got '{section}')."}
    entries = resume.get(section)
    if not isinstance(entries, list):
        entries = []
        resume[section] = entries

    if operation == "add_entry":
        if idx is not None:
            return {"error": "add_entry takes the bare section name as path, "
                             "e.g. path='projects'."}
        new_id = _new_id(resume, _ID_PREFIX[section])
        entry = {"id": new_id}
        for k, v in _ENTRY_SKELETONS[section].items():
            entry[k] = list(v) if isinstance(v, list) else v
        entry[_TITLE_FIELD[section]] = value
        entries.append(entry)
        return {"updated": True, "operation": "add_entry", "section": section,
                "new_id": new_id,
                "next": f"Fill the other fields with set on {section}[{new_id}].<field>"
                        + (f"; add bullets one by one with add on "
                           f"{section}[{new_id}].bullets" if "bullets" in entry else "")
                        + f"; reposition with move on {section}[{new_id}]."}

    if idx is None:
        return {"error": f"Use {section}[id] to address the entry, e.g. {section}[p3]."}
    entry = _find_entry(entries, idx)
    if entry is None:
        valid = [e.get("id") for e in entries if isinstance(e, dict)]
        return {"error": f"No {section} entry with id '{idx}'. Valid ids: {valid}"}

    if operation == "remove_entry":
        entries.remove(entry)
        return {"updated": True, "operation": "remove_entry", "section": section,
                "removed_id": entry.get("id"),
                "removed_title": entry.get(_TITLE_FIELD[section])}

    # move
    if value is None or not str(value).isdigit():
        return {"error": "move requires the target position as a number "
                         "(value='0' puts the entry first)."}
    entries.remove(entry)
    entries.insert(min(int(value), len(entries)), entry)
    return {"updated": True, "operation": "move", "section": section,
            "order": [e.get("id") for e in entries if isinstance(e, dict)]}


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
    Edit the resume in one call: change any field or list item, add or remove a
    whole education/experience/project entry, add or remove a bullet, or reorder
    entries within a section. The ONLY thing this tool does not do is reword
    existing bullet prose — use rewrite_bullet for that.

    Address the target with a dotted path; pick an operation:
      - set          a single value:  edit_resume("personal_info.links.github", "github.com/me", "set")
      - set          an entry field:  edit_resume("experience[e1].end_date", "2025-08", "set")
      - add / remove a list item:     edit_resume("skills.tools", "Docker", "add")
      - add_entry    a new entry:     edit_resume("projects", "AI Resume Builder", "add_entry")
                     value is the title (project name / company / school). Returns
                     new_id — then fill the other fields with set, and add bullets
                     one by one. New entries go last; reposition with move.
      - remove_entry a whole entry:   edit_resume("projects[p3]", operation="remove_entry")
      - move         an entry:        edit_resume("projects[p3]", "0", "move")  (0 = first)
      - add    a bullet (text):       edit_resume("projects[p3].bullets", "Built X using Y", "add")
      - remove a bullet (by id):      edit_resume("projects[p3].bullets", "b7", "remove")

    Valid paths:
      personal_info.{name|email|phone|location}, personal_info.links.{linkedin|github},
      skills.{languages|frameworks|tools|other}, additional.{certifications|awards},
      education[id].{school|degree|major|gpa|start_date|end_date|details},
      experience[id].{company|role|location|start_date|end_date|bullets},
      projects[id].{name|start_date|end_date|tech_stack|bullets}.
    Entry ids come from the resume; if you use a wrong id the tool returns the
    valid ids. Bullets you add are stored verbatim — they must contain only facts
    the user actually stated (polish wording afterwards with rewrite_bullet).
    Section order (education/experience/projects/...) is fixed by the template.

    Args:
        path: Dotted path to the field, list, entry, or section (see above).
        value: The value to set/add/remove, the new entry title for add_entry,
               or the target position for move. Not needed for remove_entry.
        operation: "set", "add", "remove", "add_entry", "remove_entry", or "move".

    Returns:
        A dict describing the change, or an error explaining what was wrong.
    """
    resume = tool_context.state.get("resume_json") if tool_context else None
    if not resume:
        return {"error": "No resume found in session. Please parse a resume first."}

    operation = (operation or "set").lower()
    if operation not in ("set", "add", "remove", "add_entry", "remove_entry", "move"):
        return {"error": f"operation must be set, add, remove, add_entry, "
                         f"remove_entry, or move (got '{operation}')."}
    if value is None and operation != "remove_entry":
        return {"error": f"'{operation}' requires a value."}

    if operation in ("add_entry", "remove_entry", "move"):
        result = _structural(resume, path, value, operation)
        if "error" not in result:
            # Reassign so ADK's delta-aware state records the change.
            tool_context.state["resume_json"] = resume
        return result

    holder, key, shape, err = _resolve(resume, path)
    if err:
        return {"error": err}

    extra = {}
    if shape == "bullets":
        items = holder.get(key)
        if not isinstance(items, list):
            items = []
            holder[key] = items
        if operation == "add":
            new_id = _new_id(resume, "b")
            items.append({"id": new_id, "content": value})
            extra["new_bullet_id"] = new_id
        elif operation == "remove":
            target = next((b for b in items if isinstance(b, dict)
                           and str(b.get("id")) == str(value)), None)
            if target is None:
                valid = [b.get("id") for b in items if isinstance(b, dict)]
                return {"error": f"No bullet with id '{value}' here. "
                                 f"Valid bullet ids: {valid}"}
            items.remove(target)
        else:
            return {"error": f"'{path}' holds bullets; use add (value = bullet text) "
                             f"or remove (value = bullet id). To reword an existing "
                             f"bullet use rewrite_bullet."}
    elif operation == "set":
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
            "value": value, "current": holder.get(key), **extra}
