from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def error_body(message: str, type_: str, code: str | None = None, param: str | None = None, status: int = 400):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "message": message,
                "type": type_,
                "param": param,
                "code": code,
            }
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        loc = None
        if exc.errors():
            loc = ".".join(str(x) for x in exc.errors()[0].get("loc", []) if x != "body")
        return error_body(
            message="Invalid request body",
            type_="invalid_request_error",
            code="invalid_body",
            param=loc or None,
            status=400,
        )
