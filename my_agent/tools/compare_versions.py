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
    if version_a_id == version_b_id:
        return {
            "summary": "Both IDs refer to the same version; there is nothing to compare.",
            "diff": {
                "modified_bullets": [],
                "added": [],
                "removed": [],
                "reordered": [],
            },
        }

    version_a = load_resume_version(version_a_id)
    version_b = load_resume_version(version_b_id)

    if "error" in version_a or "error" in version_b:
        return {
            "error": "Version A/B: " + version_a.get("error", "") + version_b.get("error", "")
        }
    
    # Construct the prompt for Gemini
    model = GenerativeModel(
        "gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"},
    )

    prompt = f"""You are a helpful assistant for comparing two versions of a resume. Given the structured JSON content of both versions, identify and summarize the differences between them. Return a JSON object with the following keys:
- summary: a concise 2-3 sentence plain-English summary of the key changes between the two versions
- diff: an object with the following lists:
    - modified_bullets: a list of objects for each bullet that was modified, each with:
    {{
        before: the original bullet text,
        after: the updated bullet text,
        section: the section of the resume it belongs to (e.g. 'Experience', 'Projects')
    }}
    - added: a list of description strings for any new bullets or sections added in version B
    - removed: a list of description strings for any bullets or sections removed in version B
    - reordered: a list of description strings for any bullets or sections that were moved to a different position in version B
The response MUST be valid JSON matching the structure described above, with no additional text or formatting. If you encounter any issues generating the response, return an object with empty lists and an 'error' key explaining the problem.
Version A (Baseline):
Label: {version_a['label']}
Resume JSON: {json.dumps(version_a['resume_json'])}
Version B (Updated):
Label: {version_b['label']}
Resume JSON: {json.dumps(version_b['resume_json'])}
"""
    try:
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        return data
    except json.JSONDecodeError as e:
        return {
            "summary": "",
            "diff": {
                "modified_bullets": [],
                "added": [],
                "removed": [],
                "reordered": []
            },
            "error": f"JSON decode error: {str(e)}"
        }
    
  
