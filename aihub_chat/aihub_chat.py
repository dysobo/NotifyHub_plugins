import hmac
import hashlib
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import json
import logging
import base64
import time
import os
from datetime import datetime
from pathlib import Path

import aiohttp
import aiofiles
from openai import AsyncOpenAI
from fastapi import APIRouter, Header, HTTPException, Request, Query
from fastapi.responses import FileResponse, PlainTextResponse

from notifyhub.plugins.utils import get_plugin_config
from notifyhub.controller.server import server
from notifyhub.plugins.common import after_setup

# 企业微信工具
from .wxwork_crypto import WXBizMsgCrypt, parse_wxwork_message
from .wxwork_api import WXWorkAPI


PLUGIN_ID = "aihub_chat"

# Media storage configuration
MEDIA_DIR = Path("data/plugins/aihub_chat/media")
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# Conversation history storage (简单内存存储，可扩展为数据库)
conversation_history: Dict[str, List[Dict[str, str]]] = {}
MAX_HISTORY_LENGTH = 10  # 保留最近10轮对话

# 消息去重：存储已处理的消息ID
processed_message_ids: set = set()
MAX_PROCESSED_IDS = 1000  # 最多保存1000个消息ID

aihub_chat_router = APIRouter(prefix=f"/{PLUGIN_ID}", tags=[PLUGIN_ID])
logger = logging.getLogger(__name__)


@aihub_chat_router.get("/ping")
async def ping() -> Dict[str, Any]:
    """健康检查端点"""
    return {"ok": True, "plugin": PLUGIN_ID, "version": "0.0.2"}


@aihub_chat_router.get("/status")
async def status() -> Dict[str, Any]:
    """状态检查端点"""
    config = _get_config()
    return {
        "plugin": PLUGIN_ID,
        "version": "0.0.2",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "api_base_url": config.get('api_base_url'),
            "has_api_key": bool(config.get('api_key')),
            "chat_model": config.get('chat_model'),
            "image_model": config.get('image_model'),
            "enable_web_search": config.get('enable_web_search', False),
            "enable_tts": config.get('enable_tts', False),
            "enable_stt": config.get('enable_stt', False),
            "enable_wxwork": config.get('enable_wxwork', False),
        },
        "statistics": {
            "active_conversations": len(conversation_history),
            "media_files": len(list(MEDIA_DIR.glob("*")))
        }
    }


@aihub_chat_router.post("/test")
async def test_send() -> Dict[str, Any]:
    """测试端点 - 测试企业微信连接"""
    config = _get_config()
    
    if not config.get('enable_wxwork', False):
        raise HTTPException(status_code=400, detail='企业微信未启用，请先在配置中启用')
    
    # 测试企业微信 API 连接
    wx_api = _get_wxwork_api()
    if not wx_api:
        raise HTTPException(status_code=400, detail='企业微信配置不完整')
    
    try:
        # 获取 access_token 测试连接
        token = await wx_api.get_access_token()
        if token:
            return {
                "ok": True, 
                "message": "✅ 企业微信连接正常",
                "details": {
                    "api_base": config.get('wxwork_api_base'),
                    "corp_id": config.get('wxwork_corp_id'),
                    "agent_id": config.get('wxwork_agent_id'),
                    "has_token": True,
                    "token_preview": token[:20] + "..." if len(token) > 20 else token
                }
            }
        else:
            raise HTTPException(status_code=500, detail='无法获取 access_token，请检查配置')
    except Exception as e:
        logger.error("WXWork test failed: %s", e)
        raise HTTPException(status_code=500, detail=f"测试失败: {str(e)}")


@aihub_chat_router.get("/debug/upload-test")
async def test_upload() -> Dict[str, Any]:
    """测试媒体上传功能"""
    config = _get_config()
    
    if not config.get('enable_wxwork', False):
        raise HTTPException(status_code=400, detail='企业微信未启用')
    
    wx_api = _get_wxwork_api()
    if not wx_api:
        raise HTTPException(status_code=400, detail='企业微信配置不完整')
    
    # 检查是否有测试文件
    test_files = list(MEDIA_DIR.glob("tts_*.mp3"))
    if not test_files:
        return {
            "ok": False,
            "message": "没有找到测试语音文件，请先使用 /tts 命令生成语音"
        }
    
    # 使用最新的文件测试上传
    test_file = str(test_files[-1])
    
    try:
        logger.info(f"Testing upload with file: {test_file}")
        media_id = await wx_api.upload_media(test_file, "voice")
        
        if media_id:
            return {
                "ok": True,
                "message": "✅ 上传测试成功",
                "details": {
                    "file": test_file,
                    "media_id": media_id,
                    "file_size": os.path.getsize(test_file)
                }
            }
        else:
            return {
                "ok": False,
                "message": "❌ 上传失败，请查看日志获取详细错误信息"
            }
    except Exception as e:
        logger.error(f"Upload test failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@aihub_chat_router.get("/media/{filename}")
async def get_media(filename: str):
    """提供媒体文件访问"""
    file_path = MEDIA_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Media file not found")
    return FileResponse(file_path)


@aihub_chat_router.get("/wxwork")
@aihub_chat_router.post("/wxwork")
async def wxwork_webhook(
    request: Request,
    msg_signature: str = Query(None),
    timestamp: str = Query(None),
    nonce: str = Query(None),
    echostr: str = Query(None)
) -> Any:
    """企业微信消息接收端点"""
    config = _get_config()
    
    # 检查是否启用企业微信
    if not config.get('enable_wxwork', False):
        raise HTTPException(status_code=400, detail="WXWork integration not enabled")
    
    # 获取配置
    token = config.get('wxwork_token', '')
    encoding_aes_key = config.get('wxwork_encoding_aes_key', '')
    corp_id = config.get('wxwork_corp_id', '')
    
    if not all([token, encoding_aes_key, corp_id]):
        raise HTTPException(status_code=400, detail="WXWork configuration incomplete")
    
    # 初始化加密工具
    crypto = WXBizMsgCrypt(token, encoding_aes_key, corp_id)
    
    # GET 请求 - URL 验证
    if request.method == "GET":
        if echostr:
            decrypted = crypto.verify_url(msg_signature, timestamp, nonce, echostr)
            if decrypted:
                logger.info("WXWork URL verification successful")
                return PlainTextResponse(content=decrypted)
            else:
                raise HTTPException(status_code=403, detail="Verification failed")
        else:
            raise HTTPException(status_code=400, detail="Missing echostr parameter")
    
    # POST 请求 - 接收消息
    try:
        body = await request.body()
        xml_data = body.decode('utf-8')
        
        # 解密消息
        msg_dict = crypto.decrypt_msg(msg_signature, timestamp, nonce, xml_data)
        
        if not msg_dict:
            raise HTTPException(status_code=400, detail="Decryption failed")
        
        logger.info(f"Received WXWork message: {json.dumps(msg_dict, ensure_ascii=False)}")
        
        # 处理消息
        await _handle_wxwork_message(msg_dict)
        
        # 企业微信要求返回 "success"
        return PlainTextResponse(content="success")
        
    except Exception as e:
        logger.error(f"Error processing WXWork message: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _handle_wxwork_message(msg_dict: Dict[str, Any]) -> None:
    """处理企业微信消息"""
    msg_type = msg_dict.get('MsgType', 'text')
    user_id = msg_dict.get('FromUserName', 'unknown')
    msg_id = msg_dict.get('MsgId', '')
    
    # 跳过事件类型的消息（subscribe、unsubscribe 等）
    if msg_type == 'event':
        event_type = msg_dict.get('Event', '')
        logger.info(f"Received event: {event_type} from {user_id}, skipping")
        return
    
    # 消息去重：检查是否已处理过
    if msg_id and msg_id in processed_message_ids:
        logger.info(f"Message {msg_id} already processed, skipping")
        return
    
    # 记录消息ID
    if msg_id:
        processed_message_ids.add(msg_id)
        # 控制集合大小
        if len(processed_message_ids) > MAX_PROCESSED_IDS:
            # 移除最早的一半
            to_remove = list(processed_message_ids)[:MAX_PROCESSED_IDS // 2]
            for mid in to_remove:
                processed_message_ids.discard(mid)
    
    # 获取或创建对话历史
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    
    try:
        if msg_type == 'text':
            # 文本消息
            content = msg_dict.get('Content', '')
            logger.info(f"Processing text message from {user_id}: {content}")
            await _handle_text_message(user_id, content, msg_dict, use_wxwork=True)
        elif msg_type == 'image':
            # 图片消息
            media_id = msg_dict.get('MediaId', '') or msg_dict.get('PicUrl', '')
            logger.info(f"Processing image message from {user_id}, MediaId: {media_id}")
            await _handle_wxwork_image_message(user_id, media_id, msg_dict)
        elif msg_type == 'voice':
            # 语音消息
            media_id = msg_dict.get('MediaId', '')
            logger.info(f"Processing voice message from {user_id}, MediaId: {media_id}")
            await _handle_wxwork_voice_message(user_id, media_id, msg_dict)
        else:
            logger.warning(f"Unsupported WXWork message type: {msg_type}, Full message: {msg_dict}")
            
    except Exception as e:
        logger.error(f"Error handling WXWork message: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 处理消息时出错：{str(e)}")




async def _handle_text_message(user_id: str, content: str, original_data: Dict, use_wxwork: bool = True, from_voice: bool = False) -> None:
    """处理文本消息"""
    if not content.strip():
        return
    
    # 转换为小写进行命令匹配（支持大小写不敏感）
    content_lower = content.lower()
    
    # 检查特殊命令（支持大小写）
    if content_lower.startswith('/draw ') or content_lower.startswith('/画图 '):
        # 图片生成命令
        prompt = content.split(' ', 1)[1] if ' ' in content else ''
        if prompt:
            await _generate_image(user_id, prompt, from_voice=from_voice)
        else:
            await _send_wxwork_response(user_id, "请提供图片描述，例如：/draw 一只可爱的猫咪")
        return
    
    # 智能识别绘画意图（适用于语音输入）
    is_draw = _is_draw_intent(content)
    logger.info(f"Draw intent check: '{content}' -> {is_draw}")
    
    if is_draw:
        # 提取绘画描述
        prompt = _extract_draw_prompt(content)
        logger.info(f"Extracted draw prompt: '{prompt}'")
        
        if prompt and len(prompt) > 1:  # 至少有2个字符
            logger.info(f"Generating image for: '{prompt}'")
            await _generate_image(user_id, prompt, from_voice=from_voice, original_text=content)
        else:
            logger.warning(f"Draw prompt is empty or too short: '{prompt}'")
            await _send_wxwork_response(user_id, "请告诉我您想画什么，例如：画一只可爱的猫咪")
        return
    
    # 智能识别语音合成意图
    if _is_tts_intent(content):
        # 提取要转换的文本
        text_to_speak = _extract_tts_text(content)
        if text_to_speak:
            await _text_to_speech(user_id, text_to_speak, from_voice=from_voice, original_text=content)
        else:
            await _send_wxwork_response(user_id, "请告诉我要转换什么文字，例如：朗读 你好世界")
        return
    
    if content_lower.startswith('/search ') or content_lower.startswith('/搜索 '):
        # Web 搜索命令
        query = content.split(' ', 1)[1] if ' ' in content else ''
        if query:
            await _web_search(user_id, query)
        else:
            await _send_wxwork_response(user_id, "请提供搜索关键词，例如：/search Python教程")
        return
    
    if content_lower.startswith('/tts ') or content_lower.startswith('/语音 '):
        # TTS 命令
        text = content.split(' ', 1)[1] if ' ' in content else ''
        if text:
            await _text_to_speech(user_id, text, from_voice=from_voice)
        else:
            await _send_wxwork_response(user_id, "请提供要转换的文字，例如：/tts 你好世界")
        return
    
    if content_lower.strip() in ['/clear', '/清空', '/reset', '/重置']:
        # 清空对话历史
        conversation_history[user_id] = []
        await _send_wxwork_response(user_id, "✅ 对话历史已清空")
        return
    
    # 普通对话
    await _chat(user_id, content, from_voice=from_voice)


async def _chat(user_id: str, user_message: str, from_voice: bool = False) -> None:
    """AI 对话"""
    config = _get_config()
    
    try:
        client = _get_openai_client()
        
        # 添加用户消息到历史
        conversation_history[user_id].append({
            "role": "user",
            "content": user_message
        })
        
        messages = _build_messages(user_id)
        
        response = await client.chat.completions.create(
            model=config.get('chat_model', 'gpt-4o-mini'),
            messages=messages,
            max_tokens=int(config.get('max_tokens', 2000)),
            temperature=float(config.get('temperature', 0.7))
        )
        
        ai_response = response.choices[0].message.content
        
        # 添加 AI 回复到历史
        conversation_history[user_id].append({
            "role": "assistant",
            "content": ai_response
        })
        
        # 控制历史长度
        _trim_conversation_history(user_id)
        
        # 如果是语音输入，显示识别的文本
        if from_voice:
            await _send_wxwork_response(user_id, f"🎤 {user_message}\n\n{ai_response}")
        else:
            await _send_wxwork_response(user_id, ai_response)
        
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 对话失败：{str(e)}")


async def _generate_image(user_id: str, prompt: str, from_voice: bool = False, original_text: str = None) -> None:
    """生成图片"""
    config = _get_config()
    
    try:
        client = _get_openai_client()
        
        response = await client.images.generate(
            model=config.get('image_model', 'dall-e-3'),
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        
        image_url = response.data[0].url
        
        # 下载生成的图片
        local_image = await _download_media(image_url, "generated_image")
        if local_image:
            # 企业微信：上传图片并发送
            wx_api = _get_wxwork_api()
            if wx_api:
                file_path = str(MEDIA_DIR / local_image)
                media_id = await wx_api.upload_media(file_path, "image")
                if media_id:
                    # 如果是语音输入，显示原始文本
                    if from_voice and original_text:
                        await _send_wxwork_response(user_id, f"🎤 {original_text}\n\n🎨 图片生成完成", media_id=media_id, media_type="image")
                    else:
                        await _send_wxwork_response(user_id, f"🎨 图片生成完成：\n{prompt}", media_id=media_id, media_type="image")
                else:
                    public_url = _generate_media_url(local_image)
                    await _send_wxwork_response(user_id, f"🎨 图片已生成：\n{public_url}")
            else:
                await _send_wxwork_response(user_id, "❌ 企业微信 API 未配置")
        else:
            await _send_wxwork_response(user_id, f"🎨 图片已生成：\n{image_url}")
        
    except Exception as e:
        logger.error(f"Image generation failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 图片生成失败：{str(e)}")


async def _web_search(user_id: str, query: str) -> None:
    """智能搜索 - 使用 AI 知识库回答问题"""
    config = _get_config()
    
    if not config.get('enable_web_search', False):
        await _send_wxwork_response(user_id, "❌ 智能搜索功能未启用")
        return
    
    try:
        # 使用 AIHubMix 的联网搜索功能（Tavily）
        # 在模型名称后加 :surfing 后缀，启用实时搜索
        client = _get_openai_client()
        
        base_model = config.get('chat_model', 'gpt-4o-mini')
        search_model = f"{base_model}:surfing"  # 添加 :surfing 后缀
        
        logger.info(f"Web search using model: {search_model}, query: {query}")
        
        messages = [
            {
                "role": "system", 
                "content": "你是一个智能助手，可以访问互联网搜索最新信息。请根据搜索结果提供准确的回答，尽量包含具体数据和信息来源链接。用中文回答。"
            },
            {
                "role": "user", 
                "content": query
            }
        ]
        
        response = await client.chat.completions.create(
            model=search_model,  # 使用带 :surfing 后缀的模型
            messages=messages,
            max_tokens=int(config.get('max_tokens', 2000)),
            temperature=float(config.get('temperature', 0.7))
        )
        
        search_result = response.choices[0].message.content
        
        # 记录详细日志用于调试
        logger.info(f"Search response model: {response.model}")
        logger.info(f"Search response usage: {response.usage}")
        logger.info(f"Search result preview: {search_result[:200]}...")
        
        # 检查响应中是否有搜索标记
        if hasattr(response, 'model') and response.model:
            logger.info(f"Actual model used: {response.model}")
        
        await _send_wxwork_response(user_id, f"🔍 搜索结果：\n\n{search_result}\n\n⚠️ 注：搜索功能正在测试中，结果可能不准确")
        
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 搜索失败：{str(e)}")


async def _text_to_speech(user_id: str, text: str, from_voice: bool = False, original_text: str = None) -> None:
    """文本转语音"""
    config = _get_config()
    
    if not config.get('enable_tts', False):
        await _send_wxwork_response(user_id, "❌ TTS 功能未启用")
        return
    
    try:
        client = _get_openai_client()
        
        # 生成语音（AsyncOpenAI 的方法已经是异步的）
        response = await client.audio.speech.create(
            model="tts-1",
            voice=config.get('tts_voice', 'nova'),
            input=text
        )
        
        # 保存语音文件
        timestamp = int(time.time())
        filename = f"tts_{timestamp}.mp3"
        file_path = MEDIA_DIR / filename
        
        # stream_to_file 是同步方法，需要用 to_thread
        await asyncio.to_thread(response.stream_to_file, str(file_path))
        
        # 确保文件已完全写入
        if not file_path.exists():
            logger.error(f"TTS file not found after save: {file_path}")
            await _send_wxwork_response(user_id, "❌ 语音文件保存失败")
            return
        
        file_size = os.path.getsize(file_path)
        logger.info(f"TTS file saved: {file_path}, size: {file_size} bytes")
        
        # 检查文件大小（企业微信限制 2MB）
        if file_size > 2 * 1024 * 1024:
            logger.error(f"TTS file too large: {file_size} bytes")
            await _send_wxwork_response(user_id, "❌ 语音文件过大（超过2MB限制）")
            return
        
        if file_size == 0:
            logger.error("TTS file is empty")
            await _send_wxwork_response(user_id, "❌ 语音文件为空")
            return
        
        # 企业微信：上传语音并发送
        # 注意：企业微信支持 AMR 格式，MP3 可能需要转换
        wx_api = _get_wxwork_api()
        if wx_api:
            # 尝试转换 MP3 为 AMR（企业微信推荐格式）
            amr_filename = f"tts_{timestamp}.amr"
            amr_file_path = MEDIA_DIR / amr_filename
            
            # 尝试转换为 AMR
            converted = await _convert_mp3_to_amr(str(file_path), str(amr_file_path))
            
            if converted and amr_file_path.exists():
                # 使用 AMR 文件上传
                upload_file = str(amr_file_path)
                logger.info(f"Using AMR format: {upload_file}")
            else:
                # AMR 转换失败，使用原 MP3 文件
                upload_file = str(file_path)
                logger.info(f"AMR conversion failed, using MP3: {upload_file}")
            
            logger.info(f"Uploading TTS voice file: {upload_file} ({os.path.getsize(upload_file)} bytes)")
            media_id = await wx_api.upload_media(upload_file, "voice")
            
            if media_id:
                logger.info(f"TTS voice uploaded successfully, media_id: {media_id}")
                # 直接发送语音消息
                await _send_wxwork_response(user_id, f"🔊 {text}", media_id=media_id, media_type="voice")
            else:
                # 上传失败，发送带链接的文本消息
                logger.warning(f"TTS voice upload failed, sending link instead")
                voice_url = _generate_media_url(filename)
                await _send_wxwork_response(user_id, f"🔊 语音已生成（点击链接播放）：\n{voice_url}")
        else:
            logger.error("WXWork API not configured for TTS")
            await _send_wxwork_response(user_id, "❌ 企业微信 API 未配置")
        
    except Exception as e:
        logger.error(f"TTS failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 语音合成失败：{str(e)}")


def _get_config() -> Dict[str, Any]:
    """获取插件配置"""
    return get_plugin_config(PLUGIN_ID) or {}


def _get_openai_client() -> AsyncOpenAI:
    """获取 OpenAI 客户端（兼容 AIHubMix）"""
    config = _get_config()
    
    api_key = config.get('api_key')
    if not api_key:
        raise ValueError("API Key not configured")
    
    base_url = config.get('api_base_url', 'https://aihubmix.com/v1')
    
    return AsyncOpenAI(
        api_key=api_key,
        base_url=base_url
    )


def _build_messages(user_id: str) -> List[Dict[str, Any]]:
    """构建消息列表（包含系统提示和对话历史）"""
    config = _get_config()
    system_prompt = config.get('system_prompt', '你是一个智能助手')
    
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(conversation_history.get(user_id, []))
    
    return messages


def _trim_conversation_history(user_id: str) -> None:
    """控制对话历史长度"""
    if user_id in conversation_history:
        if len(conversation_history[user_id]) > MAX_HISTORY_LENGTH * 2:
            # 保留最近的对话
            conversation_history[user_id] = conversation_history[user_id][-(MAX_HISTORY_LENGTH * 2):]


def _is_draw_intent(text: str) -> bool:
    """
    智能识别是否是绘画意图
    适用于语音输入场景，如"画一只猫"、"帮我画图"等
    """
    text_lower = text.lower().strip()
    
    # 绘画关键词列表
    draw_keywords = [
        '画', '绘画', '绘制', '画个', '画一', '画张',
        '生成图', '生成一张', '生成一幅',
        '帮我画', '给我画', '我想画',
        '创作', '设计', '制作图'
    ]
    
    # 检查是否包含绘画关键词
    for keyword in draw_keywords:
        if keyword in text_lower:
            # 排除一些误识别的情况
            exclude_keywords = ['画面', '画质', '动画', '漫画书', '看画', '挂画']
            if not any(ex in text_lower for ex in exclude_keywords):
                return True
    
    return False


def _extract_draw_prompt(text: str) -> str:
    """
    从文本中提取绘画描述
    例如："画一只可爱的猫" -> "一只可爱的猫"
    """
    text = text.strip()
    text_lower = text.lower()
    
    # 移除常见的前缀（按长度排序，先匹配长的）
    # 使用元组 (小写关键词, 原长度) 来匹配
    prefixes = [
        '帮我画一个', '给我画一个', '帮我画一只', '给我画一只',
        '生成一张图片', '生成一幅图片',
        '帮我画', '给我画', '我想画',
        '生成图片', '生成一张', '生成一幅',
        '画一个', '画一只', '画一张', '画一幅',
        '绘制一个', '绘制一只',
        '绘制', '绘画', '创作', '设计',
        '画个', '画'
    ]
    
    for prefix in prefixes:
        if text_lower.startswith(prefix):
            # 找到匹配的前缀，从原文本中提取（保留大小写）
            prompt = text[len(prefix):].strip()
            
            # 如果提取的内容不为空且有意义，返回
            if prompt and len(prompt) > 0:
                logger.info(f"Extracted draw prompt: '{text}' -> '{prompt}' (removed prefix: '{prefix}')")
                return prompt
    
    # 如果没有匹配到前缀，返回原文本
    logger.warning(f"No prefix matched for: '{text}', using full text as prompt")
    return text


def _is_tts_intent(text: str) -> bool:
    """
    智能识别是否是语音合成意图
    适用于语音输入场景，如"朗读这段文字"、"转成语音"等
    """
    text_lower = text.lower().strip()
    
    # 语音合成关键词
    tts_keywords = [
        '朗读', '读出', '语音', '念出',
        '转成语音', '转为语音', '转换成语音',
        '说出', '播放', '读一下'
    ]
    
    # 检查是否包含语音合成关键词
    for keyword in tts_keywords:
        if keyword in text_lower:
            return True
    
    return False


def _extract_tts_text(text: str) -> str:
    """
    从文本中提取要转换为语音的内容
    例如："朗读 你好世界" -> "你好世界"
    """
    text = text.strip()
    
    # 移除常见的前缀
    prefixes = [
        '帮我朗读', '给我朗读', '朗读一下',
        '转成语音', '转为语音', '转换成语音',
        '帮我读', '给我读',
        '朗读', '读出', '念出', '说出', '播放', '读一下'
    ]
    
    text_lower = text.lower()
    for prefix in prefixes:
        if text_lower.startswith(prefix):
            # 提取后面的内容
            result = text[len(prefix):].strip()
            if result:
                return result
    
    # 如果没有匹配到前缀，返回原文本
    return text


async def _download_media(url: str, media_type: str = "image") -> Optional[str]:
    """下载媒体文件"""
    try:
        if not url.startswith(('http://', 'https://')):
            logger.warning(f"Invalid media URL format: {url}")
            return None
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    logger.warning(f"Failed to download media: {url}, status: {response.status}")
                    return None
                
                timestamp = int(time.time())
                content_type = response.headers.get('content-type', '')
                
                # 确定文件扩展名
                if media_type == "image" or "image" in content_type:
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'gif' in content_type:
                        ext = '.gif'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    else:
                        ext = '.jpg'
                elif media_type == "audio" or "audio" in content_type:
                    if 'mp3' in content_type:
                        ext = '.mp3'
                    elif 'wav' in content_type:
                        ext = '.wav'
                    elif 'ogg' in content_type:
                        ext = '.ogg'
                    else:
                        ext = '.mp3'
                else:
                    ext = '.bin'
                
                filename = f"{media_type}_{timestamp}{ext}"
                file_path = MEDIA_DIR / filename
                
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
                
                logger.info(f"Downloaded media: {url} -> {filename}")
                return filename
    
    except Exception as e:
        logger.error(f"Failed to download media {url}: {e}", exc_info=True)
        return None


def _generate_media_url(filename: str) -> str:
    """生成媒体文件的公网 URL"""
    site_url = server.site_url or "http://localhost"
    return f"{site_url}/api/plugins/{PLUGIN_ID}/media/{filename}"


async def _convert_audio_format(input_path: str, output_path: str) -> bool:
    """
    转换音频格式（AMR -> MP3，用于 STT）
    :param input_path: 输入文件路径
    :param output_path: 输出文件路径
    :return: 是否转换成功
    """
    try:
        from pydub import AudioSegment
        
        logger.info(f"Converting audio: {input_path} -> {output_path}")
        
        # 在线程中执行音频转换（避免阻塞）
        def convert():
            # 尝试读取 AMR 格式
            try:
                audio = AudioSegment.from_file(input_path, format="amr")
            except:
                # 如果 AMR 失败，尝试自动检测格式
                audio = AudioSegment.from_file(input_path)
            
            # 导出为 MP3
            audio.export(output_path, format="mp3", bitrate="64k")
            return True
        
        result = await asyncio.to_thread(convert)
        logger.info(f"Audio conversion successful: {output_path}")
        return result
        
    except Exception as e:
        logger.error(f"Audio conversion failed: {e}", exc_info=True)
        return False


async def _convert_mp3_to_amr(input_path: str, output_path: str) -> bool:
    """
    转换 MP3 为 AMR 格式（用于企业微信语音消息）
    :param input_path: MP3 文件路径
    :param output_path: AMR 文件路径
    :return: 是否转换成功
    """
    logger.info(f"Converting MP3 to AMR: {input_path} -> {output_path}")
    
    # 方法 1：使用 ffmpeg 命令行（更可靠）
    try:
        import subprocess
        
        def convert_with_ffmpeg():
            # 企业微信 AMR 要求：
            # - 编码：amr_nb (AMR-NB, 窄带)
            # - 采样率：8000 Hz
            # - 单声道
            # - 比特率：12.2k
            cmd = [
                'ffmpeg',
                '-i', input_path,
                '-ar', '8000',          # 采样率 8kHz
                '-ac', '1',             # 单声道
                '-ab', '12.2k',         # 比特率
                '-acodec', 'libopencore_amrnb',  # AMR-NB 编码器
                '-y',                   # 覆盖已存在的文件
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30
            )
            
            return result.returncode == 0
        
        success = await asyncio.to_thread(convert_with_ffmpeg)
        
        if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            logger.info(f"MP3->AMR conversion successful (ffmpeg): {output_path} ({file_size} bytes)")
            return True
        else:
            logger.warning("ffmpeg conversion failed, trying pydub...")
            
    except Exception as e:
        logger.warning(f"ffmpeg conversion failed: {e}, trying pydub...")
    
    # 方法 2：使用 pydub（备用方案）
    try:
        from pydub import AudioSegment
        
        def convert_with_pydub():
            # 读取 MP3
            audio = AudioSegment.from_file(input_path, format="mp3")
            
            # 企业微信 AMR 要求
            audio = audio.set_frame_rate(8000).set_channels(1)
            
            # 导出为 AMR
            audio.export(output_path, format="amr", bitrate="12.2k")
            return True
        
        result = await asyncio.to_thread(convert_with_pydub)
        
        if result and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            file_size = os.path.getsize(output_path)
            logger.info(f"MP3->AMR conversion successful (pydub): {output_path} ({file_size} bytes)")
            return True
        
    except Exception as e:
        logger.error(f"pydub conversion also failed: {e}", exc_info=True)
    
    logger.error("All MP3->AMR conversion methods failed")
    return False


def _get_wxwork_api() -> Optional[WXWorkAPI]:
    """获取企业微信 API 客户端"""
    config = _get_config()
    
    if not config.get('enable_wxwork', False):
        return None
    
    api_base = config.get('wxwork_api_base', 'https://qyapi.weixin.qq.com')
    corp_id = config.get('wxwork_corp_id', '')
    secret = config.get('wxwork_secret', '')
    agent_id_str = config.get('wxwork_agent_id', '0')
    
    try:
        agent_id = int(agent_id_str)
    except:
        agent_id = 0
    
    if not all([corp_id, secret, agent_id]):
        logger.warning("WXWork API configuration incomplete")
        return None
    
    return WXWorkAPI(api_base, corp_id, secret, agent_id)


async def _send_wxwork_response(user_id: str, content: str, media_id: str = None, media_type: str = None) -> None:
    """通过企业微信发送响应消息"""
    wx_api = _get_wxwork_api()
    if not wx_api:
        logger.error("WXWork API not available")
        return
    
    try:
        if media_id and media_type == "image":
            # 发送图片
            success = await wx_api.send_image_message(user_id, media_id)
        elif media_id and media_type == "voice":
            # 发送语音
            success = await wx_api.send_voice_message(user_id, media_id)
        elif len(content) < 2048:
            # 发送文本（企业微信文本消息长度限制）
            success = await wx_api.send_text_message(user_id, content)
        else:
            # 超长内容分段发送
            chunks = [content[i:i+2000] for i in range(0, len(content), 2000)]
            for chunk in chunks:
                success = await wx_api.send_text_message(user_id, chunk)
                await asyncio.sleep(0.1)  # 避免频率限制
        
        if not success:
            logger.error(f"Failed to send WXWork message to {user_id}")
    except Exception as e:
        logger.error(f"Error sending WXWork response: {e}", exc_info=True)


async def _handle_wxwork_image_message(user_id: str, media_id: str, original_data: Dict) -> None:
    """处理企业微信图片消息"""
    config = _get_config()
    wx_api = _get_wxwork_api()
    
    if not wx_api:
        await _send_wxwork_response(user_id, "❌ 企业微信 API 未配置")
        return
    
    # 下载图片
    image_data = await wx_api.get_media(media_id)
    if not image_data:
        await _send_wxwork_response(user_id, "❌ 图片下载失败")
        return
    
    # 保存图片
    timestamp = int(time.time())
    filename = f"wxwork_image_{timestamp}.jpg"
    file_path = MEDIA_DIR / filename
    
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(image_data)
    
    # 转 base64 用于 AI 分析
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    
    # 使用视觉模型分析图片
    try:
        client = _get_openai_client()
        
        conversation_history[user_id].append({
            "role": "user",
            "content": [
                {"type": "text", "text": "请分析这张图片"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        })
        
        messages = _build_messages(user_id)
        
        response = await client.chat.completions.create(
            model=config.get('chat_model', 'gpt-4o-mini'),
            messages=messages,
            max_tokens=int(config.get('max_tokens', 2000)),
            temperature=float(config.get('temperature', 0.7))
        )
        
        ai_response = response.choices[0].message.content
        
        conversation_history[user_id].append({
            "role": "assistant",
            "content": ai_response
        })
        
        _trim_conversation_history(user_id)
        
        await _send_wxwork_response(user_id, f"🖼️ 图片分析：\n\n{ai_response}")
        
    except Exception as e:
        logger.error(f"WXWork image analysis failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 图片分析失败：{str(e)}")


async def _handle_wxwork_voice_message(user_id: str, media_id: str, original_data: Dict) -> None:
    """处理企业微信语音消息"""
    config = _get_config()
    
    if not config.get('enable_stt', False):
        await _send_wxwork_response(user_id, "❌ 语音识别功能未启用")
        return
    
    wx_api = _get_wxwork_api()
    if not wx_api:
        await _send_wxwork_response(user_id, "❌ 企业微信 API 未配置")
        return
    
    # 下载语音
    voice_data = await wx_api.get_media(media_id)
    if not voice_data:
        await _send_wxwork_response(user_id, "❌ 语音下载失败")
        return
    
    # 保存原始语音文件（AMR 格式）
    timestamp = int(time.time())
    amr_filename = f"wxwork_voice_{timestamp}.amr"
    amr_file_path = MEDIA_DIR / amr_filename
    
    async with aiofiles.open(amr_file_path, 'wb') as f:
        await f.write(voice_data)
    
    logger.info(f"Saved AMR file: {amr_file_path}, size: {len(voice_data)} bytes")
    
    # STT 转文本
    try:
        # 转换 AMR 为 MP3（Whisper 支持的格式）
        mp3_filename = f"wxwork_voice_{timestamp}.mp3"
        mp3_file_path = MEDIA_DIR / mp3_filename
        
        # 使用 pydub 转换音频格式
        success = await _convert_audio_format(str(amr_file_path), str(mp3_file_path))
        
        if not success:
            # 如果转换失败，尝试直接使用原文件（某些情况下可能不是真的 AMR）
            logger.warning("Audio conversion failed, trying original file")
            mp3_file_path = amr_file_path
        
        client = _get_openai_client()
        
        # AsyncOpenAI 的方法已经是异步的，直接 await
        with open(mp3_file_path, 'rb') as audio_file:
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
        
        text = transcription.text
        logger.info(f"STT result: {text}")
        
        # 重要：将识别的文本交给 _handle_text_message 处理
        # 这样可以触发智能意图识别（绘画、TTS 等）
        # 标记 from_voice=True，用于显示识别文本
        await _handle_text_message(user_id, text, original_data, use_wxwork=True, from_voice=True)
        
    except Exception as e:
        logger.error(f"WXWork STT failed: {e}", exc_info=True)
        await _send_wxwork_response(user_id, f"❌ 语音识别失败：{str(e)}")


@after_setup(plugin_id=PLUGIN_ID, desc="初始化 AIHub Chat 插件")
def init_plugin() -> None:
    """插件初始化"""
    logger.info(f"{PLUGIN_ID} plugin initialized")
    logger.info(f"Media directory: {MEDIA_DIR}")
    
    config = _get_config()
    if config.get('api_key'):
        logger.info(f"AIHubMix API configured with model: {config.get('chat_model')}")
    else:
        logger.warning(f"{PLUGIN_ID}: API Key not configured!")
    
    if config.get('enable_wxwork', False):
        logger.info("WXWork integration enabled")
    else:
        logger.info("WXWork integration disabled")

