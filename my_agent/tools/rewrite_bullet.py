import json
import re
from pathlib import Path

import yaml
from vertexai.generative_models import GenerativeModel

RUBRIC_PATH = Path(__file__).parent.parent.parent / "config" / "rubric.yaml"
MAX_RETRIES = 3

ACTION_VERBS = [
    "built", "designed", "implemented", "developed", "reduced", "improved",
    "optimized", "led", "architected", "launched", "automated", "deployed",
    "refactored", "integrated", "migrated", "trained", "analyzed",
    "collaborated", "delivered", "increased",
]


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
    raise NotImplementedError


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
    raise NotImplementedError
