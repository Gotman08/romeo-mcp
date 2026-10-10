"""Budget commun des diagnostics publics, avant serialisation MCP."""

MAX_ERROR_CHARS = 1024


def bounded_message(message: str) -> str:
    if len(message) <= MAX_ERROR_CHARS:
        return message
    suffix = " ... [diagnostic tronque]"
    return message[:MAX_ERROR_CHARS - len(suffix)] + suffix


def bound_error(result: dict) -> dict:
    """Conserve les petits diagnostics et les metadonnees de l'operation."""
    if result.get("ok") is False and isinstance(result.get("error"), str):
        message = bounded_message(result["error"])
        if message != result["error"]:
            return {**result, "error": message, "error_truncated": True}
    return result
