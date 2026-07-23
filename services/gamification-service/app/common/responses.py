"""Common response envelope utilities."""
from typing import Any, Optional
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder


def success_response(data: Any = None, status_code: int = 200, headers: Optional[dict] = None) -> JSONResponse:
    content = {
        "success": True,
        "data": data if data is not None else {},
        "error": None,
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content), headers=headers)


def error_response(
    code: str,
    message: str,
    status_code: int = 400,
    details: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> JSONResponse:
    content = {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details if details is not None else {},
        },
    }
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content), headers=headers)
