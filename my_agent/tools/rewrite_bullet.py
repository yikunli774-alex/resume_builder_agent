import json
import re
from pathlib import Path

import yaml
from google.adk.tools import ToolContext
from vertexai.generative_models import GenerativeModel

RUBRIC_PATH = Path(__file__).parent.parent.parent / "config" / "rubric.yaml"
MAX_RETRIES = 3

ACTION_VERBS = [
    "built",
    "designed",
    "implemented",
    "developed",
    "reduced",
    "improved",
    "optimized",
    "led",
    "architected",
    "launched",
    "automated",
    "deployed",
    "refactored",
    "integrated",
    "migrated",
    "trained",
    "analyzed",
    "collaborated",
    "delivered",
    "increased",
]


def _load_bad_phrases() -> list:
    """Load weak opener phrases from rubric.yaml. Returns [] if the file can't be read."""
    try:
        with open(RUBRIC_PATH) as f:
            rubric = yaml.safe_load(f)
        phrases = rubric["bullet_quality"]["starts_with_action_verb"]["bad"]
        return [p.lower() for p in phrases]
    except Exception:
        return []


BAD_PHRASES = _load_bad_phrases()


def _check_bullet_rubric(bullet: str) -> dict:
    """
    Hard-rule check on a single bullet string.

    Returns:
        {
          "passed": bool,
          "checks": {
            "has_action_verb": bool,    # first word (lowercased) is in ACTION_VERBS
            "has_quantification": bool, # contains a number or % (use regex)
            "within_length": bool       # len(bullet) <= rubric max_chars (180)
          },
          "violations": ["..."]  # human-readable explanation for each failed check
        }
    """

    words = bullet.split()
    first_word = re.sub(r"[^a-zA-Z]", "", words[0].lower()) if words else ""
    has_action_verb = first_word in ACTION_VERBS

    has_quantification = bool(re.search(r"\d+%?|\d+[kKmMbB]?\b", bullet))

    within_length = len(bullet) <= 180

    stripped = bullet.lower().lstrip("-•* \"'")
    no_weak_phrase = not any(stripped.startswith(p) for p in BAD_PHRASES)

    violations = []
    if not has_action_verb:
        violations.append("Bullet should start with a strong past-tense action verb.")
    if not has_quantification:
        violations.append(
            "Bullet should include at least one quantifiable metric (number or percentage)."
        )
    if not within_length:
        violations.append("Bullet should be under 180 characters.")
    if not no_weak_phrase:
        violations.append(
            "Bullet should not start with a weak phrase (e.g. 'Worked on', 'Responsible for')."
        )

    passed = has_action_verb and has_quantification and within_length and no_weak_phrase

    return {
        "passed": passed,
        "checks": {
            "has_action_verb": has_action_verb,
            "has_quantification": has_quantification,
            "within_length": within_length,
            "no_weak_phrase": no_weak_phrase,
        },
        "violations": violations,
    }


# Rendered-line geometry for the jakes_resume template (10pt Times, ~7.2in text
# width). Used only as a SOFT goal: the rewrite tries to hit it but is never
# failed for missing it.
LINE_CAPACITY = 90      # approx chars that fit on one rendered bullet line
ORPHAN_SECOND = 20      # a 2nd line shorter than this is 1-2 orphan words
TWO_LINE_MIN = 135      # if it wraps, aim for at least this so line 2 is >half full


def _check_line_fit(bullet: str) -> dict:
    """Soft, deterministic line-fit check (advice only — never blocks a rewrite).

    Returns {"ok": bool, "feedback": str}. `feedback` is an actionable note for
    the LLM, empty when ok. The bias is always toward TRIMMING (resumes should be
    tight), so a short single line is fine and we never tell the model to pad —
    that would invite filler/fabrication, which the truthfulness rule forbids.
    """
    n = len(bullet.strip())

    # One line is always acceptable, however short. Never pad to fill it.
    if n <= LINE_CAPACITY:
        return {"ok": True, "feedback": ""}

    second = n - LINE_CAPACITY
    if second < ORPHAN_SECOND:
        return {
            "ok": False,
            "feedback": (
                f"The bullet ({n} chars) spills only 1-2 orphan words onto a second line; "
                f"tighten the wording to fit one line (<= {LINE_CAPACITY} chars)."
            ),
        }
    if n < TWO_LINE_MIN:
        return {
            "ok": False,
            "feedback": (
                f"The bullet ({n} chars) wraps to a second line that is less than half full; "
                f"prefer tightening it to one line (<= {LINE_CAPACITY} chars). Only if the extra "
                f"detail is truthful and worth keeping, expand past {TWO_LINE_MIN} chars instead."
            ),
        }
    return {"ok": True, "feedback": ""}


def _find_bullet(resume_json: dict, bullet_id: str):
    """Locate a bullet by id across experience[] and projects[].

    Returns the bullet dict (a mutable reference living inside resume_json) so the
    caller can edit it in place, or None if no bullet with that id exists.
    """
    for section in ("experience", "projects"):
        for entry in resume_json.get(section) or []:
            for bullet in entry.get("bullets") or []:
                if bullet.get("id") == bullet_id:
                    return bullet
    return None


def rewrite_bullet(
    bullet_id: str,
    instruction: str,
    context: dict,
    tool_context: ToolContext = None,
) -> dict:
    """
    Rewrite a single resume bullet point to be stronger and more impactful, and
    persist the result back into the resume held in session state.
    Internally validates the result against a quality rubric and retries up to
    MAX_RETRIES times if the output doesn't meet the standard.
    Call this for each bullet the user has selected to improve.
    The bullet's current text is read from session state by its id — do NOT pass
    the bullet text yourself.

    Args:
        bullet_id: The id of the bullet to rewrite (from parse_resume output or
                   an analyze_jd_match suggestion's 'target' field).
        instruction: What to change, e.g. 'quantify the impact' or
                     'add specific technologies used'.
        context: Dict with optional keys:
                   experience_role (str), tech_stack (list[str]), jd_text (str).

    Returns:
        A dict with:
          - bullet_id: the id that was rewritten
          - new_bullet: the rewritten bullet (best attempt after retries), now
            also written into the resume in session state
          - previous_content: the bullet text before the rewrite
          - validation: output of _check_bullet_rubric on the final bullet
          - line_fit: output of _check_line_fit (soft wrap check; advice only,
            never affects validation/warning)
          - attempts: number of tries taken (0 if the original already passed)
          - warning: present only if rubric was not satisfied after MAX_RETRIES attempts
          - error: present only if the resume or the bullet_id could not be found

    Behavior (the retry loop — this is the core of this function):
        Read the original bullet from state, then for attempt in 1..MAX_RETRIES:
            1. Call Gemini with a prompt that includes the original bullet, instruction,
               and any available context fields (role, tech_stack, jd snippet).
            2. Strip the response to get the raw bullet string.
            3. Run _check_bullet_rubric on it.
            4. If passed → stop early.
            5. If failed → append the violations to the next attempt's prompt.
        Write the final bullet (passed, or best effort after MAX_RETRIES) back into
        state['resume_json'] and return it; include a warning if it never passed.

    Prompt rules to enforce:
        - Start with a strong past-tense action verb
        - Include at least one quantifiable metric
        - Keep under 180 characters
        - Soft line-fit goal: prefer one line (~90 chars or fewer) or, if it wraps,
          ~135+ chars so line two is over half full; avoid the ~90-135 orphan range.
          Advisory only — it never fails the bullet and never forces an extra retry;
          its feedback just rides along on retries the hard rubric already triggered.
          Biased toward trimming, never padding (truthfulness).
        - Return ONLY the bullet text, no quotes or explanation
    """
    context = context or {}

    resume_json = tool_context.state.get("resume_json") if tool_context else None
    if not resume_json:
        return {"error": "No resume found in session. Please parse a resume first."}

    bullet = _find_bullet(resume_json, bullet_id)
    if bullet is None:
        return {"error": f"Bullet id '{bullet_id}' not found in resume."}

    original_bullet = bullet.get("content", "")

    validation = _check_bullet_rubric(original_bullet)

    if validation["passed"]:
        # Already meets the rubric — leave state untouched, nothing to rewrite.
        return {
            "bullet_id": bullet_id,
            "new_bullet": original_bullet,
            "previous_content": original_bullet,
            "validation": validation,
            "attempts": 0,
        }

    new_bullet = original_bullet
    feedback = []      # hard-rubric + line-fit notes carried into the next attempt
    for attempt in range(1, MAX_RETRIES + 1):
        # Construct the prompt for Gemini
        prompt = f"Rewrite the following resume bullet to be stronger and more impactful.\n\n"
        prompt += (
            "CRITICAL TRUTHFULNESS RULE: Use ONLY facts present in the original bullet "
            "or explicitly given below. NEVER invent technologies, frameworks, tools, "
            "metrics, numbers, or details the user did not state (e.g. do not add "
            "'LangChain', '30%', etc. unless they appear in the input). You may rephrase "
            "and strengthen wording, but you must not fabricate facts. If the bullet "
            "lacks quantifiable data, improve the phrasing without inventing numbers.\n\n"
        )
        prompt += (
            "LINE-FIT GOAL (try to meet this, but it is secondary to truthfulness and the "
            "rules above): one bullet line holds about 90 characters. Prefer a single line "
            "of up to ~90 characters. If the content genuinely needs a second line, fill it "
            "past half (~135+ characters). Avoid the 90-135 range, which leaves one or two "
            "orphan words on a second line. Never pad with filler just to fill space — a "
            "short, truthful line is better than a padded one.\n\n"
        )
        prompt += f"Original Bullet: {original_bullet}\n"
        prompt += f"Instruction: {instruction}\n"
        if context.get("experience_role"):
            prompt += f"Role: {context['experience_role']}\n"
        if context.get("tech_stack"):
            prompt += f"Tech Stack: {', '.join(context['tech_stack'])}\n"
        if context.get("jd_text"):
            prompt += f"Job Description Snippet: {context['jd_text']}\n"
        if attempt > 1 and feedback:
            prompt += f"Fix these issues from the previous attempt: {' '.join(feedback)}\n"
        prompt += "Please return ONLY the rewritten bullet text, no quotes or explanations."

        # Call Gemini
        model = GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        new_bullet = response.text.strip()

        # Hard rubric (pass/fail) + soft line-fit (advice only).
        validation = _check_bullet_rubric(new_bullet)
        fit = _check_line_fit(new_bullet)

        # Stop as soon as the hard rubric passes — line-fit never triggers an
        # extra retry on its own. Its advice only rides along on retries that
        # the hard rubric already forced, nudging wrap without costing calls.
        if validation["passed"]:
            break

        # Carry both kinds of feedback into the next attempt.
        feedback = list(validation["violations"])
        if not fit["ok"]:
            feedback.append(fit["feedback"])

    # Write the final bullet (passed, or best effort) back into session state.
    # Mutate the bullet in place, then reassign the top-level key so ADK's
    # delta-aware state actually records and persists the change.
    bullet["content"] = new_bullet
    tool_context.state["resume_json"] = resume_json

    result = {
        "bullet_id": bullet_id,
        "new_bullet": new_bullet,
        "previous_content": original_bullet,
        "validation": validation,
        "line_fit": fit,
        "attempts": attempt,
    }
    if not validation["passed"]:
        result["warning"] = validation["violations"]
    return result
