import os
from datetime import datetime, timezone

from bson import ObjectId
from dotenv import load_dotenv
from google.adk.tools import ToolContext
from pymongo import MongoClient
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")


_client = None


def _get_db():
    """Return the MongoDB database instance, creating the client on first call."""
    global _client
    if _client is None:
        _client = MongoClient(os.getenv("MONGO_URI"))
    return _client[os.getenv("MONGO_DB")]


def save_resume_version(
    label: str,
    template_used: str = "jakes_resume_en",
    user_session: str = "default",
    tool_context: ToolContext = None,
) -> dict:
    """
    Save the current resume draft as a named version in MongoDB.
    Call this only when the user explicitly says they want to save their resume.
    Never call proactively. The resume is read automatically from session state —
    do NOT pass it.

    Args:
        label: Human-readable version name, e.g. 'Google SWE Intern 2026'.
        template_used: The template name used for rendering this version.
        user_session: Session ID that groups versions per user. Use 'default' if unknown.

    Returns:
        A dict with 'version_id' (MongoDB ObjectId as string) and 'created_at' (ISO timestamp).
        Returns {'error': ...} if no resume exists in the session yet.

    Behavior:
        - Read resume_json from session state.
        - Insert a document into the 'resume_versions' collection.
        - The document must include: user_session, label, template_used, created_at, resume_json.
        - Return the inserted document's _id as a string, and the timestamp as ISO format.
    """
    resume_json = (tool_context.state.get("resume_json") if tool_context else None)
    if not resume_json:
        return {"error": "No resume found in session. Please parse a resume first."}

    db = _get_db()

    doc = {
        "user_session": user_session,
        "label": label,
        "template_used": template_used,
        "created_at": datetime.now(timezone.utc),
        "resume_json": resume_json,
    }

    result = db["resume_versions"].insert_one(doc)

    return {
        "version_id": str(result.inserted_id),
        "created_at": doc["created_at"].isoformat(),
    }



def list_resume_versions(user_session: str = "default") -> dict:
    """
    Return a list of all saved resume versions for the current user session,
    sorted newest first. Does NOT include resume_json content in results.
    Call this when the user asks to see their saved resumes or version history.

    Args:
        user_session: Session ID to filter by. Use 'default' if unknown.

    Returns:
        A dict with key 'versions': a list of objects each containing
        version_id, label, created_at, and template_used.

    Behavior:
        - Query the 'resume_versions' collection filtered by user_session.
        - Exclude the resume_json field from results (keep response small).
        - Sort by created_at descending, limit 20.
        - Convert each _id to a string field named 'version_id'.
        - Convert each created_at datetime to ISO format string.
    """
    db = _get_db()

    cursor = (
        db["resume_versions"]
        .find({"user_session": user_session}, {"resume_json": 0})
        .sort("created_at", -1)
        .limit(20)
    )

    versions = []
    for doc in cursor:
        versions.append(
            {
                "version_id": str(doc["_id"]),
                "label": doc["label"],
                "template_used": doc["template_used"],
                "created_at": doc["created_at"].isoformat(),
            }
        )

    return {"versions": versions}


def load_resume_version(version_id: str) -> dict:
    """
    Load the full content of a specific saved resume version by its ID.
    Call this when the user wants to view, compare, or continue editing a past version.

    Args:
        version_id: The version ID string returned by save_resume_version or list_resume_versions.

    Returns:
        The full document including resume_json, label, template_used, and created_at.
        Returns {'error': '...'} if the version is not found or version_id is invalid.

    Behavior:
        - Look up the document by ObjectId.
        - Handle invalid ObjectId format gracefully (return error dict, don't raise).
        - Convert _id → version_id (string) and created_at → ISO string before returning.
    """
    try:
        db = _get_db()
        doc = db["resume_versions"].find_one({"_id": ObjectId(version_id)})
        if not doc:
            return {"error": "Version not found"}

        return {
            "version_id": str(doc["_id"]),
            "label": doc["label"],
            "template_used": doc["template_used"],
            "created_at": doc["created_at"].isoformat(),
            "resume_json": doc["resume_json"],
        }
    except Exception as e:
        return {"error": f"Invalid version_id: {str(e)}"}

    
