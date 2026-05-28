from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["ui"])

_CHAT_HTML_PATH = Path(__file__).with_name("chat.html")
_CHAT_HTML_TEMPLATE = _CHAT_HTML_PATH.read_text(encoding="utf-8")


@router.get("/", response_class=HTMLResponse)
@router.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request) -> HTMLResponse:
    settings = request.app.state.settings
    user_id = "local_user"
    if settings is not None:
        user_id = settings.server.chat_user_id or user_id
    html = _CHAT_HTML_TEMPLATE.replace("__CHAT_USER_ID__", user_id)
    return HTMLResponse(content=html)
