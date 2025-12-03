"""Common utility functions for Dify plugin tools."""

from datetime import datetime, timezone
from logging import Logger


def parse_timeout(
    value: object,
    default: float,
    logger: Logger | None = None,
    context: str = "operation",
) -> float:
    """Parse timeout value from tool parameters.

    Args:
        value: The timeout value from parameters (may be None, str, int, float).
        default: Default timeout value if parsing fails or value is None.
        logger: Optional logger for warning messages.
        context: Context string for log messages (e.g., "search", "get").

    Returns:
        Parsed timeout as float, or the default value.

    """
    if value is None:
        return default

    try:
        return float(value)
    except (TypeError, ValueError):
        if logger:
            logger.warning(
                "Invalid timeout value for %s: %s, using default: %s",
                context,
                value,
                default,
            )
        return default


def parse_iso_timestamp(value: object) -> datetime | None:
    """Parse ISO8601 timestamp string into timezone-aware datetime.

    Supports formats like:
    - "2025-11-03T20:06:27.669359-08:00"
    - "2025-11-03T20:06:27Z"
    - "2025-11-03T20:06:27"

    Args:
        value: The timestamp string to parse.

    Returns:
        A timezone-aware datetime object, or None if parsing fails.

    """
    if not isinstance(value, str) or not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    # Convert 'Z' suffix to '+00:00' for fromisoformat compatibility
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    # Ensure timezone-aware (assume UTC if naive)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_recent_timestamp(created_at: object, updated_at: object) -> str:
    """Return the most recent timestamp (created/updated) in second precision.

    Compares created_at and updated_at, returning whichever is more recent.
    If both are empty/invalid, returns an empty string.

    Args:
        created_at: The creation timestamp (ISO8601 string).
        updated_at: The update timestamp (ISO8601 string).

    Returns:
        Formatted timestamp string like "2025-11-03T20:06:27", or empty string.

    """
    candidates = []
    for raw in (created_at, updated_at):
        parsed = parse_iso_timestamp(raw)
        if parsed is not None:
            candidates.append(parsed)

    if not candidates:
        return ""

    latest = max(candidates, key=lambda dt: dt.timestamp())
    return latest.astimezone().strftime("%Y-%m-%dT%H:%M:%S")

