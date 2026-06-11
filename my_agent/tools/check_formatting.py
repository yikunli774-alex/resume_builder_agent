import json
import re
from pathlib import Path

import yaml
from google.adk.tools import ToolContext

RULES_PATH = Path(__file__).parent.parent.parent / "config" / "structure_rules.yaml"


def check_formatting(template_name: str = "jakes_resume_en", tool_context: ToolContext = None) -> dict:
    """
    Run hard structural rules against the current resume to catch formatting violations.
    Call this after applying suggestions to the working draft, before saving.
    The resume is read automatically from session state — do NOT pass it.

    Args:
        template_name: Reserved for future use (currently unused).

    Returns:
        A dict with:
          - passed: True if no error-severity violations found (warnings are ok)
          - violations: list of {rule_id, severity, target, message, suggestion}

    Rules to implement (load from structure_rules.yaml for reference):
        1. required_sections — error if 'personal_info' or 'education' is missing/empty
        2. personal_info_email — error if personal_info.email is missing
        3. max_page_estimate — warning if json character count > 3500
        4. max_bullets_per_experience — warning if any experience has > 5 bullets
        5. min_bullets_per_experience — warning if any experience has < 2 bullets (but > 0)
        6. max_bullets_per_project — warning if any project has > 4 bullets
        7. consistent_date_format — warning if any date doesn't match YYYY-MM or 'Present'
        8. missing_dates — warning if an education/experience/project entry has no
           start_date or end_date (empty dates render as a blank in the template)

    Behavior:
        - 'passed' is False only if at least one violation has severity == 'error'.
        - Each violation dict must have: rule_id, severity, target, message, suggestion.
        - 'target' should be specific (e.g. 'personal_info.email', 'experience.e1').
    """
    resume_json = (tool_context.state.get("resume_json") if tool_context else None)
    if not resume_json:
        return {
            "passed": False,
            "violations": [{
                "rule_id": "no_resume",
                "severity": "error",
                "target": "resume_json",
                "message": "No resume found in session. Please parse a resume first.",
                "suggestion": "Run parse_resume before checking formatting.",
            }],
        }

    violations = []

    try:
        for section in ["personal_info", "education"]:
            if not resume_json.get(section):
                violations.append({
                    "rule_id": "required_sections",
                    "severity": "error",
                    "target": section,
                    "message": f"Required section '{section}' is missing or empty.",
                    "suggestion": f"Add a '{section}' section with appropriate content.",
                })

        if not resume_json.get("personal_info", {}).get("email"):
            violations.append({
                "rule_id": "personal_info_email",
                "severity": "error",
                "target": "personal_info.email",
                "message": "Email is required in personal_info but is missing.",
                "suggestion": "Add an 'email' field under 'personal_info' with a valid email address.",
            })

        if resume_json and len(json.dumps(resume_json)) > 3500:
            violations.append({
                "rule_id": "max_page_estimate",
                "severity": "warning",
                "target": "resume_json",
                "message": "Resume content is very long and may exceed 2 pages when rendered.",
                "suggestion": "Consider condensing content to fit within 2 pages for better readability.",
            })

        for exp in resume_json.get("experience", []):
            exp_id = exp.get("id", "?")
            label = f"{exp.get('company', '?')} - {exp.get('role', '?')}"
            bullet_count = len(exp.get("bullets", []))
            if bullet_count > 5:
                violations.append({
                    "rule_id": "max_bullets_per_experience",
                    "severity": "warning",
                    "target": f"experience.{exp_id}",
                    "message": f"Experience '{label}' has {bullet_count} bullets, which may be too many.",
                    "suggestion": "Consider reducing to 5 or fewer bullets by combining or removing less important points.",
                })
            if 0 < bullet_count < 2:
                violations.append({
                    "rule_id": "min_bullets_per_experience",
                    "severity": "warning",
                    "target": f"experience.{exp_id}",
                    "message": f"Experience '{label}' has only {bullet_count} bullet, which may be too few.",
                    "suggestion": "Consider adding more details to this experience to better showcase your responsibilities and achievements.",
                })

        for proj in resume_json.get("projects", []):
            bullet_count = len(proj.get("bullets", []))
            if bullet_count > 4:
                violations.append({
                    "rule_id": "max_bullets_per_project",
                    "severity": "warning",
                    "target": f"projects.{proj.get('id', '?')}",
                    "message": f"Project '{proj.get('name', '?')}' has {bullet_count} bullets, which may be too many.",
                    "suggestion": "Consider reducing to 4 or fewer bullets by combining or removing less important points.",
                })

        for section in ["education", "experience", "projects"]:
            for entry in resume_json.get(section, []):
                for date_field in ["start_date", "end_date"]:
                    date_value = entry.get(date_field)
                    if not date_value:
                        violations.append({
                            "rule_id": "missing_dates",
                            "severity": "warning",
                            "target": f"{section}.{entry.get('id', '?')}.{date_field}",
                            "message": f"{section} entry '{entry.get('id', '?')}' has no {date_field}; it will render as a blank.",
                            "suggestion": f"Ask the user for the real date and set it via edit_resume (YYYY-MM, or 'Present' for end_date).",
                        })
                    elif not re.fullmatch(r"\d{4}-\d{2}|Present", date_value):
                        violations.append({
                            "rule_id": "consistent_date_format",
                            "severity": "warning",
                            "target": f"{section}.{entry.get('id', '?')}.{date_field}",
                            "message": f"Date '{date_value}' does not match expected format YYYY-MM or 'Present'.",
                            "suggestion": "Reformat dates to match YYYY-MM (e.g. 2020-09) or use 'Present' for current positions.",
                        })
    except Exception as e:
        return {
            "passed": False,
            "violations": [{
                "rule_id": "internal_error",
                "severity": "error",
                "target": "resume_json",
                "message": f"Formatting check failed: {e}",
                "suggestion": "Check that resume_json has the expected structure.",
            }],
        }

    passed = not any(v["severity"] == "error" for v in violations)
    return {"passed": passed, "violations": violations}
