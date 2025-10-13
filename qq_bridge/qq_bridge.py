import hmac
import hashlib
from typing import Any, Dict, List, Optional
import asyncio
import json
import logging
import urllib.parse
import time
import os
import re
import aiohttp
import aiofiles
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import FileResponse

from notifyhub.plugins.utils import get_plugin_config
from notifyhub.controller.server import server
from notifyhub.plugins.common import after_setup


PLUGIN_ID = "qq_bridge"

# Media storage configuration
MEDIA_DIR = Path("data/plugins/qq_bridge/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

qq_bridge_router = APIRouter(prefix=f"/{PLUGIN_ID}", tags=[PLUGIN_ID])
logger = logging.getLogger(__name__)

# Global WebSocket connection status and task management
_ws_status = {
    "connected": False,
    "last_connect_time": None,
    "last_disconnect_time": None,
    "connection_attempts": 0,
    "last_message_time": None,
    "total_messages": 0,
    "last_error": None
}

_ws_task: Optional[asyncio.Task] = None


@qq_bridge_router.get("/ping")
async def ping() -> Dict[str, Any]:
    return {"ok": True, "plugin": PLUGIN_ID}


@qq_bridge_router.get("/media/{filename}")
async def get_media(filename: str):
    """Serve stored media files."""
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(file_path)


@qq_bridge_router.get("/status")
async def status() -> Dict[str, Any]:
    """Debug endpoint to check plugin configuration and WebSocket status."""
    config = _get_config()
    return {
        "plugin": PLUGIN_ID,
        "timestamp": datetime.now().isoformat(),
        "websocket_status": {
            "connected": _ws_status["connected"],
            "last_connect_time": _ws_status["last_connect_time"],
            "last_disconnect_time": _ws_status["last_disconnect_time"],
            "connection_attempts": _ws_status["connection_attempts"],
            "last_message_time": _ws_status["last_message_time"],
            "total_messages": _ws_status["total_messages"],
            "last_error": _ws_status["last_error"]
        },
        "config": {
            "enable_ws": config.get('enable_ws', False),
            "onebot_ws_url": config.get('onebot_ws_url'),
            "send_target_type": config.get('send_target_type'),
            "bind_router": config.get('bind_router'),
            "bind_channel": config.get('bind_channel'),
            "allowed_groups": config.get('allowed_groups'),
            "allowed_users": config.get('allowed_users'),
            "has_access_token": bool(config.get('onebot_access_token')),
            "has_secret": bool(config.get('verify_secret')),
            "title_prefix": config.get('title_prefix')
        }
    }


@qq_bridge_router.post("/test")
async def test_send() -> Dict[str, Any]:
    """Test endpoint to send a test notification."""
    config = _get_config()
    target_type: str = (config.get('send_target_type') or 'router').strip()
    
    # Prepare test message
    title_prefix: str = config.get('title_prefix') or '[QQ群]'
    title = f"{title_prefix} [测试消息] #测试群 @测试用户"
    content = f"这是一条测试消息，发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    try:
        if target_type == 'router':
            route_id: Optional[str] = config.get('bind_router')
            if not route_id:
                raise HTTPException(status_code=400, detail='route not configured')
            server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=None, push_link_url=None)
            return {"ok": True, "message": f"Test notification sent to router: {route_id}"}
        elif target_type == 'channel':
            channel_name: Optional[str] = config.get('bind_channel')
            if not channel_name:
                raise HTTPException(status_code=400, detail='channel not configured')
            server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=None, push_link_url=None)
            return {"ok": True, "message": f"Test notification sent to channel: {channel_name}"}
        else:
            raise HTTPException(status_code=400, detail='invalid target type')
    except Exception as e:
        logger.error("Test send failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Test send failed: {str(e)}")


@qq_bridge_router.post("/test-media")
async def test_media_send() -> Dict[str, Any]:
    """Test endpoint to send a notification with media link."""
    config = _get_config()
    target_type: str = (config.get('send_target_type') or 'router').strip()
    
    # Prepare test message with media link
    title_prefix: str = config.get('title_prefix') or '[QQ群]'
    title = f"{title_prefix} [媒体测试] #测试群 @测试用户"
    content = f"这是一条包含媒体链接的测试消息，发送时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Generate a test media link
    test_link = f"https://nh.dysobo.cn:888/api/plugins/qq_bridge/media/test_image_{int(time.time())}.jpg"
    
    try:
        if target_type == 'router':
            route_id: Optional[str] = config.get('bind_router')
            if not route_id:
                raise HTTPException(status_code=400, detail='route not configured')
            server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=None, push_link_url=test_link)
            return {"ok": True, "message": f"Test media notification sent to router: {route_id}", "test_link": test_link}
        elif target_type == 'channel':
            channel_name: Optional[str] = config.get('bind_channel')
            if not channel_name:
                raise HTTPException(status_code=400, detail='channel not configured')
            server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=None, push_link_url=test_link)
            return {"ok": True, "message": f"Test media notification sent to channel: {channel_name}", "test_link": test_link}
        else:
            raise HTTPException(status_code=400, detail='invalid target type')
    except Exception as e:
        logger.error("Test media send failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Test media send failed: {str(e)}")


@qq_bridge_router.get("/debug/last-message")
async def get_last_message() -> Dict[str, Any]:
    """Get the last received message for debugging."""
    return {
        "last_message": getattr(get_last_message, '_last_message', None),
        "timestamp": getattr(get_last_message, '_last_timestamp', None)
    }


@qq_bridge_router.get("/diagnose")
async def diagnose_connection() -> Dict[str, Any]:
    """Diagnose WebSocket connection issues."""
    config = _get_config()
    onebot_ws_url: str = config.get('onebot_ws_url') or 'ws://127.0.0.1:3001/'
    
    # Parse URL to get HTTP equivalent
    import urllib.parse
    parsed = urllib.parse.urlparse(onebot_ws_url)
    http_url = f"http://{parsed.netloc}{parsed.path}"
    
    diagnosis = {
        "websocket_url": onebot_ws_url,
        "http_equivalent": http_url,
        "current_status": _ws_status,
        "suggestions": []
    }
    
    # Add suggestions based on current error
    last_error = _ws_status.get("last_error", "") or ""
    if "did not receive a valid HTTP response" in last_error:
        diagnosis["suggestions"].extend([
            "检查 NapCat WebSocket 服务是否正在运行",
            "确认端口号是否正确（通常是 3001 或 4001）",
            "尝试访问 HTTP 版本确认服务可达性",
            "检查 NapCat 配置中的 WebSocket 设置",
            "常见 WebSocket 路径: ws://ip:port/ 或 ws://ip:port/ws"
        ])
    elif "Connection refused" in last_error:
        diagnosis["suggestions"].extend([
            "NapCat 服务未启动或端口被占用",
            "检查防火墙设置",
            "确认 IP 地址和端口号"
        ])
    elif "timeout" in last_error.lower():
        diagnosis["suggestions"].extend([
            "网络连接超时，检查网络连通性",
            "NapCat 服务响应缓慢"
        ])
    
    # Add NapCat configuration examples
    diagnosis["napcat_config_examples"] = {
        "websocket_server": {
            "enable": True,
            "host": "0.0.0.0",
            "port": 4001
        },
        "websocket_reverse": {
            "enable": False
        }
    }
    
    return diagnosis


@qq_bridge_router.get("/test-api")
async def test_onebot_api() -> Dict[str, Any]:
    """Test OneBot HTTP API connectivity and file API."""
    config = _get_config()
    
    # Try to get HTTP API base URL (same logic as _get_onebot_file_url)
    api_base = None
    
    # Option 1: Use dedicated HTTP API URL if configured
    onebot_http_api = config.get('onebot_http_api', '').strip()
    if onebot_http_api:
        api_base = onebot_http_api.rstrip('/')
    
    # Option 2: Convert WebSocket URL to HTTP API URL (if WebSocket is enabled)
    elif config.get('enable_ws', False):
        onebot_ws_url = config.get('onebot_ws_url', 'ws://127.0.0.1:3001/')
        if onebot_ws_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(onebot_ws_url)
            api_base = f"http://{parsed.netloc}"
    
    access_token = config.get('onebot_access_token', '')
    
    results = {
        "api_base": api_base,
        "has_access_token": bool(access_token),
        "endpoints_tested": [],
        "errors": [],
        "config_status": {
            "enable_ws": config.get('enable_ws', False),
            "has_onebot_ws_url": bool(config.get('onebot_ws_url', '').strip()),
            "has_onebot_http_api": bool(config.get('onebot_http_api', '').strip())
        }
    }
    
    # If no API base URL available, return early with explanation
    if not api_base:
        results["message"] = "无法测试 OneBot API：未配置 HTTP API 地址。请配置 'OneBot HTTP API 地址' 或启用 WebSocket 并配置 WS 地址。"
        return results
    
    headers = {}
    if access_token:
        headers['Authorization'] = f'Bearer {access_token}'
    
    # Test different endpoints
    test_endpoints = [
        f"{api_base}/",  # Root endpoint
        f"{api_base}/get_status",  # Status endpoint
        f"{api_base}/get_version_info",  # Version info
        f"{api_base}/get_file",  # File API (will fail without file_id, but shows if endpoint exists)
        f"{api_base}/api/get_file",  # Alternative file API
    ]
    
    async with aiohttp.ClientSession() as session:
        for endpoint in test_endpoints:
            try:
                async with session.get(endpoint, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    result = {
                        "endpoint": endpoint,
                        "status": response.status,
                        "headers": dict(response.headers),
                        "accessible": response.status in [200, 400, 422]  # 400/422 means endpoint exists but missing params
                    }
                    
                    # Try to get response text for small responses
                    try:
                        if response.headers.get('content-length'):
                            content_length = int(response.headers.get('content-length', 0))
                            if content_length < 1000:  # Only read small responses
                                result["response"] = await response.text()
                    except:
                        pass
                    
                    results["endpoints_tested"].append(result)
                    
            except Exception as e:
                results["errors"].append({
                    "endpoint": endpoint,
                    "error": str(e)
                })
    
    return results


def _get_config() -> Dict[str, Any]:
    return get_plugin_config(PLUGIN_ID) or {}


def _is_group_allowed(group_id: Optional[str], allowed_str: Optional[str]) -> bool:
    if not allowed_str:
        return True
    if not group_id:
        return False
    allowed = {g.strip() for g in allowed_str.split(',') if g.strip()}
    return group_id in allowed


def _is_user_allowed(user_id: Optional[str], allowed_str: Optional[str]) -> bool:
    if not allowed_str:
        return True
    if not user_id:
        return False
    allowed = {u.strip() for u in allowed_str.split(',') if u.strip()}
    return user_id in allowed


async def _get_onebot_file_url(file_id: str, file_type: str = "image") -> Optional[str]:
    """Get file URL from OneBot API using file ID."""
    config = _get_config()
    
    # Try to get HTTP API base URL
    api_base = None
    
    # Option 1: Use dedicated HTTP API URL if configured
    onebot_http_api = config.get('onebot_http_api', '').strip()
    if onebot_http_api:
        api_base = onebot_http_api.rstrip('/')
    
    # Option 2: Convert WebSocket URL to HTTP API URL (if WebSocket is enabled)
    elif config.get('enable_ws', False):
        onebot_ws_url = config.get('onebot_ws_url', 'ws://127.0.0.1:3001/')
        if onebot_ws_url:
            import urllib.parse
            parsed = urllib.parse.urlparse(onebot_ws_url)
            api_base = f"http://{parsed.netloc}"
    
    # If no API base URL available, cannot proceed
    if not api_base:
        logger.debug("No OneBot HTTP API URL configured, cannot resolve file_id: %s", file_id)
        return None
    
    logger.info("Attempting to resolve file_id '%s' using API base: %s", file_id, api_base)
    
    access_token = config.get('onebot_access_token', '')
    
    try:
        headers = {}
        if access_token:
            headers['Authorization'] = f'Bearer {access_token}'
        
        # Try different OneBot API endpoints for file URLs
        endpoints = [
            f"{api_base}/get_file",  # OneBot 12 standard
            f"{api_base}/api/get_file",  # Some implementations
            f"{api_base}/get_image",  # NapCat specific for images
            f"{api_base}/get_record",  # NapCat specific for audio
        ]
        
        async with aiohttp.ClientSession() as session:
            for endpoint in endpoints:
                try:
                    # Try GET request first with different parameter names
                    params = {'file_id': file_id}
                    async with session.get(endpoint, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        logger.debug("GET %s returned status %d", endpoint, response.status)
                        if response.status == 200:
                            data = await response.json()
                            logger.debug("GET %s response: %s", endpoint, data)
                            # OneBot 12 response format
                            if 'data' in data and 'url' in data['data']:
                                return data['data']['url']
                            # Alternative response formats
                            elif 'url' in data:
                                return data['url']
                            elif 'file' in data:
                                return data['file']
                            # NapCat response format
                            elif 'data' in data and isinstance(data['data'], str):
                                return data['data']
                    
                    # Try POST request if GET fails
                    if response.status in [404, 405]:
                        # Try different parameter names for NapCat
                        for param_name in ['file_id', 'file', 'url']:
                            payload = {param_name: file_id}
                            async with session.post(endpoint, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as post_response:
                                logger.debug("POST %s with %s returned status %d", endpoint, payload, post_response.status)
                                if post_response.status == 200:
                                    data = await post_response.json()
                                    logger.debug("POST %s response: %s", endpoint, data)
                                    # Check for error response first
                                    if data.get('code') == -1 or data.get('status') == 'error':
                                        logger.debug("API returned error: %s", data.get('message', 'Unknown error'))
                                        continue
                                    
                                    # OneBot 12 response format
                                    if 'data' in data and 'url' in data['data']:
                                        return data['data']['url']
                                    # NapCat response format
                                    elif 'data' in data and isinstance(data['data'], dict):
                                        if 'url' in data['data']:
                                            return data['data']['url']
                                        elif 'file' in data['data']:
                                            return data['data']['file']
                                    # Alternative response formats
                                    elif 'url' in data:
                                        return data['url']
                                    elif 'file' in data:
                                        return data['file']
                                    # Direct string response
                                    elif 'data' in data and isinstance(data['data'], str):
                                        return data['data']
                                    
                except Exception as e:
                    logger.warning("Failed to get file URL from %s: %s", endpoint, e)
                    continue
        
        logger.warning("Could not get file URL for file_id: %s - All API endpoints failed", file_id)
        return None
        
    except Exception as e:
        logger.error("Error getting OneBot file URL for %s: %s", file_id, e)
        return None


async def _download_media(url: str, media_type: str = "image") -> Optional[str]:
    """Download media file and return local filename."""
    try:
        # Check if URL is valid
        if not url.startswith(('http://', 'https://')):
            logger.warning("Invalid media URL format: %s", url)
            return None
            
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.warning("Failed to download media: %s, status: %d", url, response.status)
                    return None
                
                # Generate filename
                timestamp = int(time.time())
                content_type = response.headers.get('content-type', '')
                
                # Determine file extension
                if media_type == "image":
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'gif' in content_type:
                        ext = '.gif'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    else:
                        ext = '.jpg'  # default
                elif media_type == "audio":
                    if 'mp3' in content_type:
                        ext = '.mp3'
                    elif 'wav' in content_type:
                        ext = '.wav'
                    elif 'ogg' in content_type:
                        ext = '.ogg'
                    else:
                        ext = '.mp3'  # default
                elif media_type == "video":
                    if 'mp4' in content_type:
                        ext = '.mp4'
                    elif 'avi' in content_type:
                        ext = '.avi'
                    else:
                        ext = '.mp4'  # default
                else:
                    ext = '.bin'  # unknown type
                
                filename = f"{media_type}_{timestamp}{ext}"
                file_path = MEDIA_DIR / filename
                
                # Save file
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                
                logger.info("Downloaded media: %s -> %s", url, filename)
                return filename
                
    except Exception as e:
        logger.error("Failed to download media %s: %s", url, e)
        return None


def _generate_media_url(filename: str, base_url: str = "https://nh.dysobo.cn:888") -> str:
    """Generate public URL for media file."""
    return f"{base_url}/api/plugins/qq_bridge/media/{filename}"


def _verify_signature(secret: Optional[str], raw_body: bytes, x_signature: Optional[str]) -> bool:
    # OneBot/Go-CQHTTP X-Signature usually is sha1=...
    if not secret:
        return True
    if not x_signature:
        return False
    try:
        mac = hmac.new(secret.encode('utf-8'), msg=raw_body, digestmod=hashlib.sha1)
        expected = 'sha1=' + mac.hexdigest()
        return hmac.compare_digest(expected, x_signature)
    except Exception:
        return False


async def _parse_message_segments(message: List[Dict[str, Any]]) -> tuple[str, Optional[str], List[str]]:
    """Parse OneBot message segments into text, image URL, and media links."""
    text_parts: List[str] = []
    image_url: Optional[str] = None
    media_links: List[str] = []
    
    for segment in message:
        if not isinstance(segment, dict):
            continue
            
        segment_type = segment.get('type', '')
        data = segment.get('data', {})
        
        if segment_type == 'text':
            text_parts.append(data.get('text', ''))
        elif segment_type == 'image':
            # OneBot 12 image URL
            file_url = data.get('file') or data.get('url')
            if file_url:
                # Check if it's a valid URL or just a filename/file_id
                if file_url.startswith(('http://', 'https://')):
                    # Direct URL - download and store image
                    filename = await _download_media(file_url, "image")
                    if filename:
                        media_url = _generate_media_url(filename)
                        media_links.append(f"🖼️ 图片: {media_url}")
                        image_url = media_url  # For push_img_url
                        text_parts.append('[图片]')
                    else:
                        # Download failed, but show original URL for enterprise WeChat
                        media_links.append(f"🖼️ 图片: {file_url}")
                        text_parts.append('[图片]')
                else:
                    # Filename or file_id - try to get URL from OneBot API
                    logger.debug("Attempting to get URL for file_id/filename: %s", file_url)
                    onebot_url = await _get_onebot_file_url(file_url, "image")
                    
                    if onebot_url and onebot_url.startswith(('http://', 'https://')):
                        # Successfully got URL from OneBot API
                        filename = await _download_media(onebot_url, "image")
                        if filename:
                            media_url = _generate_media_url(filename)
                            media_links.append(f"🖼️ 图片: {media_url}")
                            image_url = media_url
                            text_parts.append('[图片]')
                        else:
                            # Download failed, show OneBot URL
                            media_links.append(f"🖼️ 图片: {onebot_url}")
                            text_parts.append('[图片]')
                    else:
                        # Could not get URL from OneBot API
                        # Show more detailed information for debugging
                        media_links.append(f"🖼️ 图片: 文件名 {file_url}")
                        media_links.append(f"   📋 文件ID: {file_url}")
                        media_links.append(f"   🔗 尝试获取: OneBot API 调用失败")
                        text_parts.append('[图片]')
            else:
                text_parts.append('[图片]')
        elif segment_type == 'record':
            # Voice message
            file_url = data.get('file') or data.get('url')
            if file_url:
                if file_url.startswith(('http://', 'https://')):
                    filename = await _download_media(file_url, "audio")
                    if filename:
                        media_url = _generate_media_url(filename)
                        media_links.append(f"🎵 语音: {media_url}")
                        text_parts.append('[语音]')
                    else:
                        # Download failed, but show original URL for enterprise WeChat
                        media_links.append(f"🎵 语音: {file_url}")
                        text_parts.append('[语音]')
                else:
                    # Filename or file_id - try to get URL from OneBot API
                    logger.debug("Attempting to get URL for audio file_id/filename: %s", file_url)
                    onebot_url = await _get_onebot_file_url(file_url, "audio")
                    
                    if onebot_url and onebot_url.startswith(('http://', 'https://')):
                        # Successfully got URL from OneBot API
                        filename = await _download_media(onebot_url, "audio")
                        if filename:
                            media_url = _generate_media_url(filename)
                            media_links.append(f"🎵 语音: {media_url}")
                            text_parts.append('[语音]')
                        else:
                            # Download failed, show OneBot URL
                            media_links.append(f"🎵 语音: {onebot_url}")
                            text_parts.append('[语音]')
                    else:
                        # Could not get URL from OneBot API
                        media_links.append(f"🎵 语音: 文件名 {file_url} (无法获取下载链接)")
                        text_parts.append('[语音]')
            else:
                text_parts.append('[语音]')
        elif segment_type == 'video':
            # Video message
            file_url = data.get('file') or data.get('url')
            if file_url:
                if file_url.startswith(('http://', 'https://')):
                    filename = await _download_media(file_url, "video")
                    if filename:
                        media_url = _generate_media_url(filename)
                        media_links.append(f"🎬 视频: {media_url}")
                        text_parts.append('[视频]')
                    else:
                        # Download failed, but show original URL for enterprise WeChat
                        media_links.append(f"🎬 视频: {file_url}")
                        text_parts.append('[视频]')
                else:
                    # Filename or file_id - try to get URL from OneBot API
                    logger.debug("Attempting to get URL for video file_id/filename: %s", file_url)
                    onebot_url = await _get_onebot_file_url(file_url, "video")
                    
                    if onebot_url and onebot_url.startswith(('http://', 'https://')):
                        # Successfully got URL from OneBot API
                        filename = await _download_media(onebot_url, "video")
                        if filename:
                            media_url = _generate_media_url(filename)
                            media_links.append(f"🎬 视频: {media_url}")
                            text_parts.append('[视频]')
                        else:
                            # Download failed, show OneBot URL
                            media_links.append(f"🎬 视频: {onebot_url}")
                            text_parts.append('[视频]')
                    else:
                        # Could not get URL from OneBot API
                        media_links.append(f"🎬 视频: 文件名 {file_url} (无法获取下载链接)")
                        text_parts.append('[视频]')
            else:
                text_parts.append('[视频]')
        elif segment_type == 'face':
            # QQ emoji
            face_id = data.get('id', '')
            text_parts.append(f'[表情:{face_id}]')
        elif segment_type == 'at':
            # @ mention
            user_id = data.get('qq', '')
            text_parts.append(f'@{user_id}')
        elif segment_type == 'reply':
            # Reply to message
            reply_id = data.get('id', '')
            text_parts.append(f'[回复:{reply_id}]')
        elif segment_type == 'file':
            # File message
            text_parts.append('[文件]')
        elif segment_type == 'location':
            # Location
            lat = data.get('lat', '')
            lon = data.get('lon', '')
            text_parts.append(f'[位置:{lat},{lon}]')
        elif segment_type == 'share':
            # Link share
            title = data.get('title', '')
            text_parts.append(f'[分享:{title}]')
        else:
            # Unknown segment type
            text_parts.append(f'[{segment_type}]')
    
    return ''.join(text_parts), image_url, media_links


@qq_bridge_router.post("/webhook")
async def webhook(request: Request, x_signature: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    raw = await request.body()
    config = _get_config()

    if not _verify_signature(config.get("verify_secret"), raw, x_signature):
        raise HTTPException(status_code=403, detail="invalid signature")

    try:
        data = await request.json()
        # Store last message for debugging
        get_last_message._last_message = data
        get_last_message._last_timestamp = datetime.now().isoformat()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")

    # Expect OneBot v11 'message' event
    if data.get('post_type') != 'message':
        return {"ok": True, "skipped": True}

    message_type = data.get('message_type')
    if message_type == 'group':
        group_id = str(data.get('group_id')) if data.get('group_id') is not None else None
        if not _is_group_allowed(group_id, config.get('allowed_groups')):
            raise HTTPException(status_code=403, detail="group not allowed")
    elif message_type == 'private':
        user_id = str(data.get('user_id')) if data.get('user_id') is not None else None
        if not _is_user_allowed(user_id, config.get('allowed_users')):
            raise HTTPException(status_code=403, detail="user not allowed")
    else:
        return {"ok": True, "skipped": True}

    user_id = data.get('user_id')
    # Parse message segments for rich content
    message_segments = data.get('message', [])
    if isinstance(message_segments, list):
        parsed_text, image_url, media_links = await _parse_message_segments(message_segments)
    else:
        # Fallback to raw_message if message is not a list
        parsed_text = data.get('raw_message') or ''
        image_url = None
        media_links = []
    
    # Build title based on message type
    title_prefix: str = config.get('title_prefix') or '[QQ群]'
    if message_type == 'group':
        group_name = data.get('group_name') or ''
        nickname = (data.get('sender') or {}).get('nickname') or ''
        title = f"{title_prefix} #{group_name or group_id} @{nickname or user_id}"
    else:  # private message
        nickname = (data.get('sender') or {}).get('nickname') or ''
        title = f"[私聊] @{nickname or user_id}"
    
    # Add media links to content for enterprise WeChat
    content = parsed_text
    push_link_url: Optional[str] = None
    
    if media_links:
        # 提取第一个媒体链接作为可点击链接
        first_media_link = media_links[0]
        # 从链接文本中提取URL
        url_match = re.search(r'https?://[^\s]+', first_media_link)
        if url_match:
            push_link_url = url_match.group()
            logger.info("qq_bridge extracted clickable link: %s", push_link_url)
        
        # 如果只有一个媒体文件，简化内容显示
        if len(media_links) == 1:
            content += f"\n\n📎 {first_media_link.split(':', 1)[0] if ':' in first_media_link else '媒体文件'}"
        else:
            content += "\n\n📎 媒体文件:\n" + "\n".join(media_links)

    target_type: str = (config.get('send_target_type') or 'router').strip()
    if target_type == 'router':
        route_id: Optional[str] = config.get('bind_router')
        if not route_id:
            raise HTTPException(status_code=400, detail='route not configured')
        server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=image_url, push_link_url=push_link_url)
    elif target_type == 'channel':
        channel_name: Optional[str] = config.get('bind_channel')
        if not channel_name:
            raise HTTPException(status_code=400, detail='channel not configured')
        server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=image_url, push_link_url=push_link_url)
    else:
        raise HTTPException(status_code=400, detail='invalid target type')

    return {"ok": True}


# ========== OneBot 12 WebSocket Listener ==========
async def _ws_loop(onebot_ws_url: str, access_token: Optional[str], allowed_groups: Optional[str], allowed_users: Optional[str], target_type: str, route_id: Optional[str], channel_name: Optional[str], title_prefix: str) -> None:
    import websockets  # type: ignore

    headers = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    retry_count = 0
    max_retries = 3
    
    while True:
        try:
            logger.info("qq_bridge attempting WS connection to: %s", onebot_ws_url)
            _ws_status["connection_attempts"] += 1
            
            async with websockets.connect(onebot_ws_url, additional_headers=headers, ping_interval=30, ping_timeout=30) as ws:
                logger.info("qq_bridge WS connected successfully: %s", onebot_ws_url)
                _ws_status["connected"] = True
                _ws_status["last_connect_time"] = datetime.now().isoformat()
                _ws_status["last_error"] = None
                retry_count = 0  # Reset retry count on successful connection
                
                async for msg in ws:
                    _ws_status["last_message_time"] = datetime.now().isoformat()
                    _ws_status["total_messages"] += 1
                    
                    try:
                        data = json.loads(msg)
                        logger.debug("qq_bridge WS received: %s", data)
                    except Exception as e:
                        logger.warning("qq_bridge WS failed to parse JSON: %s", e)
                        continue
                    
                    # Log all received events for debugging
                    post_type = data.get('post_type')
                    message_type = data.get('message_type')
                    logger.debug("qq_bridge WS event: post_type=%s, message_type=%s", post_type, message_type)
                    
                    # Expect message events; adapt if OneBot emits different envelope
                    if post_type != 'message':
                        logger.debug("qq_bridge WS skipping non-message event")
                        continue
                    
                    # Check message type and permissions
                    if message_type == 'group':
                        group_id = str(data.get('group_id')) if data.get('group_id') is not None else None
                        if not _is_group_allowed(group_id, allowed_groups):
                            logger.debug("qq_bridge WS group %s not allowed", group_id)
                            continue
                    elif message_type == 'private':
                        user_id_check = str(data.get('user_id')) if data.get('user_id') is not None else None
                        if not _is_user_allowed(user_id_check, allowed_users):
                            logger.debug("qq_bridge WS user %s not allowed", user_id_check)
                            continue
                    else:
                        logger.debug("qq_bridge WS skipping unsupported message type: %s", message_type)
                        continue
                    user_id = data.get('user_id')
                    # Parse message segments for rich content
                    message_segments = data.get('message', [])
                    if isinstance(message_segments, list):
                        parsed_text, image_url, media_links = await _parse_message_segments(message_segments)
                    else:
                        parsed_text = data.get('raw_message') or ''
                        image_url = None
                        media_links = []
                    
                    # Build title based on message type
                    if message_type == 'group':
                        group_name = data.get('group_name') or ''
                        nickname = (data.get('sender') or {}).get('nickname') or ''
                        title = f"{title_prefix} #{group_name or group_id} @{nickname or user_id}"
                    else:  # private message
                        nickname = (data.get('sender') or {}).get('nickname') or ''
                        title = f"[私聊] @{nickname or user_id}"
                    
                    # Add media links to content for enterprise WeChat
                    content = parsed_text
                    push_link_url: Optional[str] = None
                    
                    if media_links:
                        # 提取第一个媒体链接作为可点击链接
                        first_media_link = media_links[0]
                        # 从链接文本中提取URL
                        url_match = re.search(r'https?://[^\s]+', first_media_link)
                        if url_match:
                            push_link_url = url_match.group()
                            logger.info("qq_bridge WS extracted clickable link: %s", push_link_url)
                        
                        # 如果只有一个媒体文件，简化内容显示
                        if len(media_links) == 1:
                            content += f"\n\n📎 {first_media_link.split(':', 1)[0] if ':' in first_media_link else '媒体文件'}"
                        else:
                            content += "\n\n📎 媒体文件:\n" + "\n".join(media_links)
                    
                    logger.info("qq_bridge WS forwarding message: type=%s, user=%s, content=%s", message_type, user_id, parsed_text[:50])
                    
                    try:
                        if target_type == 'router' and route_id:
                            server.send_notify_by_router(route_id=route_id, title=title, content=content, push_img_url=image_url, push_link_url=push_link_url)
                            logger.info("qq_bridge WS sent to router: %s", route_id)
                        elif target_type == 'channel' and channel_name:
                            server.send_notify_by_channel(channel_name=channel_name, title=title, content=content, push_img_url=image_url, push_link_url=push_link_url)
                            logger.info("qq_bridge WS sent to channel: %s", channel_name)
                        else:
                            logger.warning("qq_bridge WS no valid target configured")
                    except Exception as e:
                        logger.error("qq_bridge WS failed to send notification: %s", e)
                logger.warning("qq_bridge WS closed: %s", onebot_ws_url)
                _ws_status["connected"] = False
                _ws_status["last_disconnect_time"] = datetime.now().isoformat()
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning("qq_bridge WS connection closed: %s", e)
            _ws_status["connected"] = False
            _ws_status["last_disconnect_time"] = datetime.now().isoformat()
            _ws_status["last_error"] = f"Connection closed: {str(e)}"
        except websockets.exceptions.InvalidURI as e:
            logger.error("qq_bridge WS invalid URI: %s", e)
            _ws_status["connected"] = False
            _ws_status["last_error"] = f"Invalid URI: {str(e)}"
            break  # Don't retry on invalid URI
        except websockets.exceptions.InvalidHandshake as e:
            logger.error("qq_bridge WS handshake failed: %s", e)
            logger.error("qq_bridge WS URL: %s, Headers: %s", onebot_ws_url, headers)
            _ws_status["connected"] = False
            _ws_status["last_error"] = f"Handshake failed: {str(e)}"
            retry_count += 1
            if retry_count >= max_retries:
                logger.error("qq_bridge WS max retries reached, stopping WebSocket listener")
                break
        except Exception as e:
            logger.error("qq_bridge WS error: %s", e)
            _ws_status["connected"] = False
            _ws_status["last_error"] = f"General error: {str(e)}"
            retry_count += 1
            if retry_count >= max_retries:
                logger.error("qq_bridge WS max retries reached, stopping WebSocket listener")
                break
        
        if retry_count < max_retries:
            wait_time = min(5 * (retry_count + 1), 30)  # Exponential backoff, max 30s
            logger.info("qq_bridge WS retrying in %d seconds...", wait_time)
            await asyncio.sleep(wait_time)
        else:
            logger.error("qq_bridge WS connection failed permanently, stopping")
            break


@after_setup(plugin_id=PLUGIN_ID, desc="启动 OneBot WebSocket 监听")
def start_ws_listener() -> None:
    global _ws_task
    
    config = _get_config()
    if not config.get('enable_ws', False):
        logger.info("qq_bridge WebSocket listening disabled, using HTTP webhook only")
        return
    
    onebot_ws_url: str = config.get('onebot_ws_url') or 'ws://127.0.0.1:3001/'
    access_token: Optional[str] = config.get('onebot_access_token')
    target_type: str = (config.get('send_target_type') or 'router').strip()
    route_id: Optional[str] = config.get('bind_router')
    channel_name: Optional[str] = config.get('bind_channel')
    allowed_groups: Optional[str] = config.get('allowed_groups')
    allowed_users: Optional[str] = config.get('allowed_users')
    title_prefix: str = config.get('title_prefix') or '[QQ群]'

    logger.info("qq_bridge WebSocket config: url=%s, target_type=%s, route_id=%s, channel_name=%s, allowed_groups=%s", 
                onebot_ws_url, target_type, route_id, channel_name, allowed_groups)

    # Validate configuration
    if target_type == 'router' and not route_id:
        logger.error("qq_bridge WebSocket: router target selected but no route_id configured")
        return
    if target_type == 'channel' and not channel_name:
        logger.error("qq_bridge WebSocket: channel target selected but no channel_name configured")
        return

    # run in background task via server's event loop
    try:
        loop = asyncio.get_event_loop()
        _ws_task = loop.create_task(_ws_loop(onebot_ws_url, access_token, allowed_groups, allowed_users, target_type, route_id, channel_name, title_prefix))
        logger.info("qq_bridge WebSocket listener task created successfully")
    except Exception as e:
        logger.error("qq_bridge WebSocket failed to create listener task: %s", e)


