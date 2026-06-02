import json

from vertexai.generative_models import GenerativeModel


def analyze_jd_match(resume_json: dict, jd_text: str) -> dict:
    """
    Analyze how well a resume matches a job description. Returns an overall
    match score, keyword coverage, and a prioritized list of improvement suggestions.
    Call this after parse_resume, once the user has also provided a job description.

    Args:
        resume_json: Structured resume data — the output of parse_resume.
        jd_text: The full text of the target job description.

    Returns:
        A dict with:
          - match_score: integer 0-100
          - keyword_coverage: {covered: [...], missing: [...]}
          - experience_relevance: [{experience_id, score, reason}, ...]
          - suggestions: [{id, description, target, type, impact_score}, ...]
            where type is one of: rewrite | reorder | add | remove | quantify

    Behavior:
        - Call Gemini with a prompt that includes both resume_json (as JSON string)
          and jd_text.
        - Ask Gemini to return ONLY valid JSON matching the output shape above.
        - Provide 5-8 suggestions sorted by impact_score descending.
        - Handle JSON parse errors gracefully: return the shape with empty lists
          and an 'error' key explaining what went wrong.

    Prompt tip: Tell Gemini to be specific — cite the exact bullet id or section
    name in each suggestion's 'target' field.
    """
    structered_resume = json.dumps(resume_json)
    model = GenerativeModel(
        "gemini-2.5-flash",
        generation_config={"response_mime_type": "application/json"},
    )
    try:
        response = model.generate_content(
            f"""Given the following structured resume JSON and job description text, analyze how well the resume matches the job description. Return a JSON object with the following keys:
- match_score: an integer from 0 to 100 indicating overall relevance
- keyword_coverage: an object with two lists, 'covered' and 'missing', listing key skills or keywords from the JD that are present or absent in the resume
- experience_relevance: a list of objects for each experience entry in the resume, each with:
  - experience_id: the unique ID of the experience entry
  - score: relevance score from 0 to 100 for that experience
  - reason: a brief explanation of why it received that score
- suggestions: a prioritized list of 5-8 specific improvement suggestions, each with:
  - id: a short unique ID for the suggestion
  - description: a clear description of the suggested improvement
  - target: the specific section or bullet ID in the resume that the suggestion applies to
  - type: one of 'rewrite', 'reorder', 'add', 'remove', or 'quantify'
  - impact_score: an integer from 0 to 100 indicating the potential impact of the suggestion on improving the match
The response MUST be valid JSON matching the structure described above, with no additional text or formatting. If you encounter any issues generating the response, return an object with empty lists and an 'error' key explaining the problem.
Resume JSON:
{structered_resume}
Job Description:
{jd_text}
"""
        )
        data = json.loads(response.text)
        data["suggestions"] = sorted(
            data.get("suggestions", []),
            key=lambda s: s.get("impact_score", 0),
            reverse=True,
        )[:8]
        return data
    except json.JSONDecodeError as e:
        return {
            "match_score": 0,
            "keyword_coverage": {"covered": [], "missing": []},
            "experience_relevance": [],
            "suggestions": [],
            "error": f"Failed to parse model response as JSON: {str(e)}",
        }

