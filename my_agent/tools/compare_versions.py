import json

from vertexai.generative_models import GenerativeModel

from .mongo_tools import load_resume_version


def compare_versions(version_a_id: str, version_b_id: str) -> dict:
    """
    Compare two saved resume versions and summarize what changed between them.
    Call this when the user asks to compare or diff two versions.

    Args:
        version_a_id: The version ID of the older / baseline version.
        version_b_id: The version ID of the newer / updated version.

    Returns:
        A dict with:
          - summary: 2-3 sentence plain-English summary of the changes
          - diff: {
              modified_bullets: [{before, after, section}],
              added: [description strings],
              removed: [description strings],
              reordered: [description strings]
            }
          - error: present only if one or both versions could not be loaded

    Behavior:
        1. Call load_resume_version for both IDs.
        2. If either returns an 'error' key, propagate it and return early.
        3. Build a Gemini prompt that includes both resume JSONs and their labels.
        4. Ask Gemini to return ONLY valid JSON matching the output shape above.
        5. Handle JSON parse errors gracefully (return shape with empty lists + error key).
    """
    raise NotImplementedError
