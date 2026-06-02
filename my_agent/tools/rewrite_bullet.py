import json
import re
from pathlib import Path

import yaml
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


def rewrite_bullet(original_bullet: str, instruction: str, context: dict) -> dict:
    """
    Rewrite a single resume bullet point to be stronger and more impactful.
    Internally validates the result against a quality rubric and retries up to
    MAX_RETRIES times if the output doesn't meet the standard.
    Call this for each bullet the user has selected to improve.

    Args:
        original_bullet: The current bullet text to rewrite.
        instruction: What to change, e.g. 'quantify the impact' or
                     'add specific technologies used'.
        context: Dict with optional keys:
                   experience_role (str), tech_stack (list[str]), jd_text (str).

    Returns:
        A dict with:
          - new_bullet: the rewritten bullet (best attempt after retries)
          - validation: output of _check_bullet_rubric on the final bullet
          - attempts: number of tries taken (1 to MAX_RETRIES)
          - warning: present only if rubric was not satisfied after MAX_RETRIES attempts

    Behavior (the retry loop — this is the core of this function):
        for attempt in 1..MAX_RETRIES:
            1. Call Gemini with a prompt that includes original_bullet, instruction,
               and any available context fields (role, tech_stack, jd snippet).
            2. Strip the response to get the raw bullet string.
            3. Run _check_bullet_rubric on it.
            4. If passed → return immediately with attempts count.
            5. If failed → append the violations to the instruction for the next attempt.
        After MAX_RETRIES, return the last attempt's bullet with a warning.

    Prompt rules to enforce:
        - Start with a strong past-tense action verb
        - Include at least one quantifiable metric
        - Keep under 180 characters
        - Return ONLY the bullet text, no quotes or explanation
    """
    validation = _check_bullet_rubric(original_bullet)

    if validation["passed"]:
        return {
            "new_bullet": original_bullet,
            "validation": validation,
            "attempts": 0,
        }

    else:
        for attempt in range(1, MAX_RETRIES + 1):
            # Construct the prompt for Gemini
            prompt = f"Rewrite the following resume bullet to be stronger and more impactful.\n\n"
            prompt += f"Original Bullet: {original_bullet}\n"
            prompt += f"Instruction: {instruction}\n"
            if context.get("experience_role"):
                prompt += f"Role: {context['experience_role']}\n"
            if context.get("tech_stack"):
                prompt += f"Tech Stack: {', '.join(context['tech_stack'])}\n"
            if context.get("jd_text"):
                prompt += f"Job Description Snippet: {context['jd_text']}\n"
            if attempt > 1:
                prompt += f"Previous attempt failed checks: {', '.join(validation['violations'])}\n"
            prompt += "Please return ONLY the rewritten bullet text, no quotes or explanations."

            # Call Gemini
            model = GenerativeModel(
                "gemini-2.5-flash"
            )  # Implement this function to call Gemini
            response = model.generate_content(prompt)
            new_bullet = response.text.strip()

            # Validate the new bullet against the rubric
            validation = _check_bullet_rubric(new_bullet)

            if validation["passed"]:
                return {
                    "new_bullet": new_bullet,
                    "validation": validation,
                    "attempts": attempt,
                }

        # If we exhaust all attempts without passing, return the last attempt with a warning
        return {
            "new_bullet": new_bullet,
            "validation": validation,
            "attempts": MAX_RETRIES,
            "warning": validation["violations"],
        }
