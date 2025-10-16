"""
企业微信 API 工具
用于主动发送消息、获取媒体文件等
"""

import aiohttp
import logging
import time
import json
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class WXWorkAPI:
    """企业微信 API 客户端"""

    def __init__(self, api_base: str, corp_id: str, secret: str, agent_id: int):
        """
        初始化
        :param api_base: API 基础地址
        :param corp_id: 企业ID
        :param secret: 应用Secret
        :param agent_id: 应用AgentID
        """
        self.api_base = api_base.rstrip('/')
        self.corp_id = corp_id
        self.secret = secret
        self.agent_id = agent_id
        
        self._access_token = None
        self._token_expires_at = 0

    async def get_access_token(self) -> Optional[str]:
        """
        获取 access_token（带缓存）
        :return: access_token 或 None
        """
        # 检查缓存
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token
        
        # 获取新 token
        url = f"{self.api_base}/cgi-bin/gettoken"
        params = {
            "corpid": self.corp_id,
            "corpsecret": self.secret
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    data = await response.json()
                    
                    if data.get("errcode") == 0:
                        self._access_token = data.get("access_token")
                        # 提前5分钟过期
                        self._token_expires_at = time.time() + data.get("expires_in", 7200) - 300
                        logger.info("WXWork access_token refreshed")
                        return self._access_token
                    else:
                        logger.error(f"Failed to get access_token: {data}")
                        return None
        except Exception as e:
            logger.error(f"Error getting access_token: {e}", exc_info=True)
            return None

    async def send_text_message(self, user_id: str, content: str) -> bool:
        """
        发送文本消息
        :param user_id: 用户ID
        :param content: 消息内容
        :return: 是否成功
        """
        access_token = await self.get_access_token()
        if not access_token:
            return False
        
        url = f"{self.api_base}/cgi-bin/message/send"
        params = {"access_token": access_token}
        
        data = {
            "touser": user_id,
            "msgtype": "text",
            "agentid": self.agent_id,
            "text": {
                "content": content
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result = await response.json()
                    
                    if result.get("errcode") == 0:
                        logger.info(f"Sent text message to {user_id}")
                        return True
                    else:
                        logger.error(f"Failed to send message: {result}")
                        return False
        except Exception as e:
            logger.error(f"Error sending text message: {e}", exc_info=True)
            return False

    async def send_markdown_message(self, user_id: str, content: str) -> bool:
        """
        发送 Markdown 消息
        :param user_id: 用户ID
        :param content: Markdown 内容
        :return: 是否成功
        """
        access_token = await self.get_access_token()
        if not access_token:
            return False
        
        url = f"{self.api_base}/cgi-bin/message/send"
        params = {"access_token": access_token}
        
        data = {
            "touser": user_id,
            "msgtype": "markdown",
            "agentid": self.agent_id,
            "markdown": {
                "content": content
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result = await response.json()
                    
                    if result.get("errcode") == 0:
                        logger.info(f"Sent markdown message to {user_id}")
                        return True
                    else:
                        logger.error(f"Failed to send markdown: {result}")
                        return False
        except Exception as e:
            logger.error(f"Error sending markdown message: {e}", exc_info=True)
            return False

    async def send_image_message(self, user_id: str, media_id: str) -> bool:
        """
        发送图片消息
        :param user_id: 用户ID
        :param media_id: 媒体文件ID
        :return: 是否成功
        """
        access_token = await self.get_access_token()
        if not access_token:
            return False
        
        url = f"{self.api_base}/cgi-bin/message/send"
        params = {"access_token": access_token}
        
        data = {
            "touser": user_id,
            "msgtype": "image",
            "agentid": self.agent_id,
            "image": {
                "media_id": media_id
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result = await response.json()
                    
                    if result.get("errcode") == 0:
                        logger.info(f"Sent image message to {user_id}")
                        return True
                    else:
                        logger.error(f"Failed to send image: {result}")
                        return False
        except Exception as e:
            logger.error(f"Error sending image message: {e}", exc_info=True)
            return False

    async def send_voice_message(self, user_id: str, media_id: str) -> bool:
        """
        发送语音消息
        :param user_id: 用户ID
        :param media_id: 媒体文件ID
        :return: 是否成功
        """
        access_token = await self.get_access_token()
        if not access_token:
            return False
        
        url = f"{self.api_base}/cgi-bin/message/send"
        params = {"access_token": access_token}
        
        data = {
            "touser": user_id,
            "msgtype": "voice",
            "agentid": self.agent_id,
            "voice": {
                "media_id": media_id
            }
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params, json=data, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    result = await response.json()
                    
                    if result.get("errcode") == 0:
                        logger.info(f"Sent voice message to {user_id}")
                        return True
                    else:
                        logger.error(f"Failed to send voice: {result}")
                        return False
        except Exception as e:
            logger.error(f"Error sending voice message: {e}", exc_info=True)
            return False

    async def upload_media(self, file_path: str, media_type: str = "image") -> Optional[str]:
        """
        上传临时素材
        :param file_path: 文件路径
        :param media_type: 媒体类型 (image/voice/video/file)
        :return: media_id 或 None
        """
        access_token = await self.get_access_token()
        if not access_token:
            logger.error("No access_token available for upload")
            return None
        
        url = f"{self.api_base}/cgi-bin/media/upload"
        params = {
            "access_token": access_token,
            "type": media_type
        }
        
        logger.info(f"Uploading media: {file_path}, type: {media_type}")
        
        try:
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return None
            
            file_size = os.path.getsize(file_path)
            logger.info(f"File size: {file_size} bytes")
            
            async with aiohttp.ClientSession() as session:
                with open(file_path, 'rb') as f:
                    # 使用 multipart/form-data 上传
                    data = aiohttp.FormData()
                    filename = os.path.basename(file_path)
                    data.add_field('media', 
                                   f, 
                                   filename=filename,
                                   content_type='application/octet-stream')
                    
                    logger.info(f"Uploading to: {url}, params: {params}")
                    
                    async with session.post(url, params=params, data=data, timeout=aiohttp.ClientTimeout(total=60)) as response:
                        response_text = await response.text()
                        logger.info(f"Upload response: {response_text}")
                        
                        try:
                            result = json.loads(response_text)
                        except:
                            logger.error(f"Failed to parse JSON response: {response_text}")
                            return None
                        
                        if result.get("errcode") == 0 or "media_id" in result:
                            media_id = result.get("media_id")
                            logger.info(f"Successfully uploaded media: {media_id}, type: {media_type}")
                            return media_id
                        else:
                            logger.error(f"Failed to upload media. Error code: {result.get('errcode')}, Message: {result.get('errmsg')}")
                            return None
        except Exception as e:
            logger.error(f"Error uploading media {file_path}: {e}", exc_info=True)
            return None

    async def get_media(self, media_id: str) -> Optional[bytes]:
        """
        获取临时素材
        :param media_id: 媒体文件ID
        :return: 文件内容（bytes）或 None
        """
        access_token = await self.get_access_token()
        if not access_token:
            return None
        
        url = f"{self.api_base}/cgi-bin/media/get"
        params = {
            "access_token": access_token,
            "media_id": media_id
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 200:
                        content = await response.read()
                        logger.info(f"Downloaded media: {media_id}")
                        return content
                    else:
                        logger.error(f"Failed to download media: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading media: {e}", exc_info=True)
            return None

