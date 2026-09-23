"""Le format d'erreur, écrit une fois.

    {"error": {"code": "...", "message": "...", "details": {...}}}

Un code nommé plutôt qu'un statut seul : « 422 » ne dit pas à l'écran s'il faut
proposer un autre fournisseur ou réclamer une justification.
"""

from __future__ import annotations

from fastapi.responses import JSONResponse


def error_response(
    status: int, code: str, message: str, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )
