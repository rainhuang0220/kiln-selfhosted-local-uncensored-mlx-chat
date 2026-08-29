from __future__ import annotations

from typing import Annotated

from fastapi import Request

from app.services.chat import ChatService


def get_chat(request: Request) -> ChatService:
    return request.app.state.chat


ChatDep = Annotated[ChatService, ...]
