"""Event provenance helpers."""

from urllib.parse import quote


def event_source_ref(relative_filename: str) -> str:
    """Return the only permitted event source URI shape."""

    return f"local://event-wiki/{quote(relative_filename, safe='/')}"
