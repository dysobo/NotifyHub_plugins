from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from notifyhub.plugins.utils import get_plugin_config
from notifyhub.controller.server import server


PLUGIN_ID = "syno_chat_webhook"


syno_chat_router = APIRouter(prefix=f"/{PLUGIN_ID}", tags=[PLUGIN_ID])


class SynologyChatPayload(BaseModel):
    token: Optional[str] = None
    team_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    text: Optional[str] = None
    timestamp: Optional[str] = None
    # Accept and store any additional fields transparently
    class Config:
        extra = "allow"


def _get_config() -> Dict[str, Any]:
    config = get_plugin_config(PLUGIN_ID) or {}
    return config


def _is_channel_allowed(channel_name: Optional[str], allowed_str: Optional[str]) -> bool:
    if not allowed_str:
        return True
    if not channel_name:
        return False
    allowed_list: List[str] = [name.strip() for name in allowed_str.split(",") if name.strip()]
    return channel_name in allowed_list


@syno_chat_router.get("/ping")
async def ping() -> Dict[str, Any]:
    return {"ok": True, "plugin": PLUGIN_ID}


async def _parse_payload(request: Request) -> Dict[str, Any]:
    # Try JSON
    try:
        if request.headers.get("content-type", "").lower().startswith("application/json"):
            data = await request.json()
            if isinstance(data, dict):
                return data
    except Exception:
        pass

    # Try form/multipart
    try:
        if "application/x-www-form-urlencoded" in request.headers.get("content-type", "").lower() or \
           "multipart/form-data" in request.headers.get("content-type", "").lower():
            form = await request.form()
            return {k: (v if isinstance(v, str) else str(v)) for k, v in form.items()}
    except Exception:
        pass

    # Fallback: raw body as querystring
    try:
        raw = await request.body()
        if raw:
            from urllib.parse import parse_qs
            parsed = {k: v[0] if isinstance(v, list) and v else v for k, v in parse_qs(raw.decode("utf-8")).items()}
            if parsed:
                return parsed
    except Exception:
        pass

    return {}


@syno_chat_router.post("/webhook")
async def webhook(request: Request, x_forwarded_for: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    incoming = await _parse_payload(request)
    try:
        payload = SynologyChatPayload.model_validate(incoming)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid payload")

    config = _get_config()

    verify_token: Optional[str] = config.get("verify_token")
    if verify_token:
        if (payload.token or incoming.get("token")) != verify_token:
            raise HTTPException(status_code=403, detail="invalid token")

    if not _is_channel_allowed(payload.channel_name, config.get("allowed_channels")):
        raise HTTPException(status_code=403, detail="channel not allowed")

    title_prefix: str = config.get("title_prefix") or "[Synology Chat]"
    title_parts: List[str] = [title_prefix]
    if payload.channel_name:
        title_parts.append(f"#{payload.channel_name}")
    if payload.username:
        title_parts.append(f"@{payload.username}")
    title = " ".join(title_parts)

    content_lines: List[str] = []
    if payload.text:
        content_lines.append(payload.text)
    else:
        content_lines.append("(no text)")

    # Include minimal context
    meta: List[str] = []
    if payload.timestamp:
        meta.append(f"time: {payload.timestamp}")
    if payload.team_id:
        meta.append(f"team: {payload.team_id}")
    if meta:
        content_lines.append("\n" + " | ".join(meta))

    content = "\n".join(content_lines)

    target_type: str = (config.get("send_target_type") or "router").strip()

    if target_type == "router":
        route_id: Optional[str] = config.get("bind_router")
        if not route_id:
            raise HTTPException(status_code=400, detail="route not configured")
        server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=None, push_link_url=None)
    elif target_type == "channel":
        channel_name: Optional[str] = config.get("bind_channel")
        if not channel_name:
            raise HTTPException(status_code=400, detail="channel not configured")
        server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=None, push_link_url=None)
    else:
        raise HTTPException(status_code=400, detail="invalid target type")

    return {"ok": True}



