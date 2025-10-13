#!/usr/bin/env python3
"""
企业微信MeTube下载器插件
通过企业微信接收YouTube链接，自动提交到MeTube下载，完成后推送下载链接
"""

import datetime
import threading
import httpx
import logging
import re
import time
import asyncio
import os
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from cacheout import Cache
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import Response
from xml.etree.ElementTree import fromstring
from tenacity import wait_random_exponential, stop_after_attempt, retry

from notifyhub.plugins.components.qywx_Crypt.WXBizMsgCrypt import WXBizMsgCrypt
from notifyhub.common.response import json_500
from notifyhub.plugins.utils import get_plugin_config
from notifyhub.controller.server import server
from notifyhub.plugins.common import after_setup
from notifyhub.controller.schedule import register_cron_job

from .utils import config

logger = logging.getLogger(__name__)

# 插件信息
PLUGIN_ID = "wx_metube"
PLUGIN_NAME = "企业微信MeTube下载器"

# 缓存配置
token_cache = Cache(maxsize=1)
download_cache = Cache(maxsize=5000, ttl=86400)  # 下载记录缓存24小时
processed_downloads_cache = Cache(maxsize=10000, ttl=604800)  # 已处理下载缓存7天

# 图片缓存目录
IMAGE_CACHE_DIR = Path("/data/plugins/wx_metube/images")
IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# FastAPI路由器
wx_metube_router = APIRouter(prefix="/wx_metube", tags=["wx_metube"])

APP_USER_AGENT = "wx-metube/1.0.0"
XML_TEMPLATES = {
    "reply": """<xml>
<ToUserName><![CDATA[{to_user}]]></ToUserName>
<FromUserName><![CDATA[{from_user}]]></FromUserName>
<CreateTime>{create_time}</CreateTime>
<MsgType><![CDATA[{msg_type}]]></MsgType>
<Content><![CDATA[{content}]]></Content>
<MsgId>{msg_id}</MsgId>
<AgentID>{agent_id}</AgentID>
</xml>"""
}

@dataclass
class QywxMessage:
    """企业微信消息数据类"""
    content: str
    from_user: str
    to_user: str
    create_time: str
    msg_type: str
    msg_id: str

@dataclass
class DownloadTask:
    """下载任务数据类"""
    url: str
    title: str
    user_id: str
    submit_time: datetime.datetime
    download_id: str
    status: str = "submitted"
    filename: Optional[str] = None
    download_url: Optional[str] = None
    last_check_time: Optional[datetime.datetime] = None
    check_count: int = 0
    next_check_interval: int = 10  # 初始检查间隔（秒）

class QywxMessageSender:
    """企业微信消息发送器"""
    
    def __init__(self):
        self.base_url = config.qywx_base_url
        self.corpid = config.sCorpID
        self.corpsecret = config.sCorpsecret
        self.agentid = config.sAgentid
    
    @retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=10, max=30), reraise=True)
    def get_access_token(self) -> Optional[str]:
        """获取企业微信访问令牌"""
        # 检查缓存中的token是否有效
        cached_token = token_cache.get('access_token')
        expires_time = token_cache.get('expires_time')
        
        if (expires_time is not None and 
            expires_time >= datetime.datetime.now() and 
            cached_token):
            return cached_token
        
        if not all([self.corpid, self.corpsecret]):
            logger.error("企业微信配置错误")
            return None
        
        # 重新获取token
        try:
            # 构建请求参数
            request_params = {
                'corpid': self.corpid,
                'corpsecret': self.corpsecret
            }
            
            # 准备请求配置
            request_config = {
                'headers': {'user-agent': APP_USER_AGENT},
                'timeout': 30
            }
            
            # 如果有代理配置，添加到请求中
            proxy_config = config.get_proxy_config()
            if proxy_config:
                request_config['proxies'] = proxy_config
            
            response = httpx.get(
                f"{self.base_url.strip('/')}/cgi-bin/gettoken",
                params=request_params,
                **request_config
            )
            
            result = response.json()
            if result.get('errcode') == 0:
                access_token = result['access_token']
                expires_in = result['expires_in']
                
                # 计算过期时间（提前500秒刷新）
                expires_time = datetime.datetime.now() + datetime.timedelta(
                    seconds=expires_in - 500
                )
                
                # 缓存token和过期时间
                token_cache.set('access_token', access_token, ttl=expires_in - 500)
                token_cache.set('expires_time', expires_time, ttl=expires_in - 500)
                
                logger.info("企业微信access_token获取成功")
                return access_token
            else:
                logger.error(f"获取企业微信accessToken失败: {result}")
                return None
                
        except Exception as e:
            logger.error(f"获取企业微信accessToken异常: {e}")
            return None
    
    @retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=10, max=30), reraise=True)
    def _send_message(self, access_token: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """发送消息到企业微信"""
        try:
            url = f"{self.base_url.strip('/')}/cgi-bin/message/send"
            params = {'access_token': access_token}
            
            # 准备请求配置
            request_config = {
                'headers': {'user-agent': APP_USER_AGENT},
                'timeout': 30
            }
            
            # 如果有代理配置，添加到请求中
            proxy_config = config.get_proxy_config()
            if proxy_config:
                request_config['proxies'] = proxy_config
            
            response = httpx.post(
                url,
                params=params,
                json=message_data,
                **request_config
            )
            
            return response.json()
            
        except Exception as e:
            logger.error(f"发送企业微信消息异常: {e}")
            return {'errcode': -1, 'errmsg': str(e)}
    
    def send_text_message(self, text: str, to_user: str) -> bool:
        """发送文本消息"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("获取企业微信accessToken失败")
            return False
        
        message_data = {
            'touser': to_user,
            'agentid': self.agentid,
            'msgtype': 'text',
            'text': {'content': text}
        }
        
        result = self._send_message(access_token, message_data)
        
        if result.get('errcode') == 0:
            logger.info(f"企业微信消息发送成功: {to_user}")
            return True
        else:
            logger.error(f"发送企业微信消息失败: {result}")
            return False
    
    def send_news_message(self, articles: List[Dict[str, str]], to_user: str) -> bool:
        """发送图文消息"""
        access_token = self.get_access_token()
        if not access_token:
            logger.error("获取企业微信accessToken失败")
            return False
        
        message_data = {
            'touser': to_user,
            'agentid': self.agentid,
            'msgtype': 'news',
            'news': {'articles': articles}
        }
        
        result = self._send_message(access_token, message_data)
        
        if result.get('errcode') == 0:
            logger.info(f"企业微信图文消息发送成功: {to_user}")
            return True
        else:
            logger.error(f"发送企业微信图文消息失败: {result}")
            return False

class ImageCacheManager:
    """图片缓存管理器"""
    
    def __init__(self):
        self.cache_dir = IMAGE_CACHE_DIR
        self.session = httpx.Client(timeout=30)
    
    def download_and_cache_image(self, image_url: str, video_id: str = None) -> Optional[str]:
        """下载并缓存图片，返回本地URL"""
        try:
            if not image_url:
                return None
            
            # 生成缓存文件名
            if video_id:
                filename = f"{video_id}.jpg"
            else:
                # 使用URL的hash作为文件名
                url_hash = hashlib.md5(image_url.encode()).hexdigest()
                filename = f"{url_hash}.jpg"
            
            cache_path = self.cache_dir / filename
            
            # 如果文件已存在，直接返回
            if cache_path.exists():
                local_url = self._get_local_image_url(filename)
                logger.info(f"图片已缓存: {filename} -> {local_url}")
                return local_url
            
            # 下载图片
            logger.info(f"下载图片: {image_url}")
            response = self.session.get(image_url, timeout=30)
            
            if response.status_code == 200:
                # 保存到本地
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
                
                local_url = self._get_local_image_url(filename)
                logger.info(f"图片缓存成功: {filename} -> {local_url}")
                return local_url
            else:
                logger.error(f"图片下载失败: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"图片缓存异常: {e}")
            return None
    
    def _get_local_image_url(self, filename: str) -> str:
        """获取本地图片的访问URL"""
        # 从NotifyHub配置中获取正确的服务地址
        # 使用NotifyHub的站点地址而不是MeTube的地址
        try:
            from notifyhub.controller.server import server
            site_url = server.site_url
            if not site_url:
                # 如果无法获取站点地址，使用默认配置
                base_url = config.metube_url.replace(':8081', ':888')
            else:
                base_url = site_url.rstrip('/')
        except Exception as e:
            logger.warning(f"无法获取NotifyHub站点地址，使用默认配置: {e}")
            base_url = config.metube_url.replace(':8081', ':888')
        
        return f"{base_url}/api/plugins/wx_metube/images/{filename}"
    
    def cleanup_old_images(self, max_age_days: int = 7):
        """清理过期的缓存图片"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for file_path in self.cache_dir.glob("*.jpg"):
                if current_time - file_path.stat().st_mtime > max_age_seconds:
                    file_path.unlink()
                    logger.info(f"清理过期图片: {file_path.name}")
                    
        except Exception as e:
            logger.error(f"清理图片缓存异常: {e}")

class YouTubeInfoExtractor:
    """YouTube视频信息提取器"""
    
    def __init__(self):
        self.session = httpx.Client(timeout=30)
        self.image_cache = ImageCacheManager()
    
    def extract_video_info(self, url: str) -> Dict[str, Any]:
        """提取YouTube视频信息"""
        try:
            # 使用yt-dlp提取视频信息
            import subprocess
            import json
            
            cmd = [
                'yt-dlp',
                '--dump-json',
                '--no-download',
                '--quiet',
                url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                video_info = json.loads(result.stdout)
                
                # 提取视频ID用于缓存
                video_id = video_info.get('id', '')
                thumbnail_url = video_info.get('thumbnail', '')
                
                # 缓存封面图片
                local_thumbnail_url = None
                if thumbnail_url:
                    logger.info(f"开始缓存图片: {thumbnail_url}")
                    local_thumbnail_url = self.image_cache.download_and_cache_image(thumbnail_url, video_id)
                    logger.info(f"图片缓存结果: 原始URL={thumbnail_url}, 本地URL={local_thumbnail_url}")
                
                return {
                    'title': video_info.get('title', '未知标题'),
                    'thumbnail': local_thumbnail_url or thumbnail_url,  # 优先使用本地缓存
                    'original_thumbnail': thumbnail_url,  # 保留原始URL
                    'duration': video_info.get('duration', 0),
                    'uploader': video_info.get('uploader', '未知上传者'),
                    'view_count': video_info.get('view_count', 0),
                    'upload_date': video_info.get('upload_date', ''),
                    'video_id': video_id,
                    'success': True
                }
            else:
                logger.warning(f"yt-dlp提取视频信息失败: {result.stderr}")
                return {'success': False, 'error': result.stderr}
                
        except subprocess.TimeoutExpired:
            logger.warning("yt-dlp提取视频信息超时")
            return {'success': False, 'error': '提取超时'}
        except Exception as e:
            logger.warning(f"提取YouTube视频信息异常: {e}")
            return {'success': False, 'error': str(e)}

class MeTubeClient:
    """MeTube客户端"""
    
    def __init__(self):
        self.base_url = config.metube_url
        self.session = httpx.Client(timeout=60)  # 增加超时时间到60秒
        self.youtube_extractor = YouTubeInfoExtractor()
    
    @retry(stop=stop_after_attempt(3), wait=wait_random_exponential(min=2, max=10), reraise=True)
    def submit_download(self, url: str, quality: str = None, format: str = None, 
                       auto_start: bool = None) -> Dict[str, Any]:
        """提交下载任务到MeTube"""
        try:
            submit_data = {
                "url": url,
                "quality": quality or config.default_quality,
                "format": format or config.default_format,
                "auto_start": auto_start if auto_start is not None else config.auto_start
            }
            
            logger.info(f"提交下载到MeTube: {url}")
            response = self.session.post(f"{self.base_url}/add", json=submit_data)
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"MeTube下载提交成功: {result}")
                return result
            else:
                logger.error(f"MeTube下载提交失败: {response.status_code} - {response.text}")
                return {"status": "error", "msg": f"HTTP {response.status_code}"}
                
        except Exception as e:
            logger.error(f"提交MeTube下载异常: {e}")
            return {"status": "error", "msg": str(e)}
    
    @retry(stop=stop_after_attempt(2), wait=wait_random_exponential(min=1, max=5), reraise=True)
    def get_download_status(self) -> Dict[str, Any]:
        """获取下载状态"""
        try:
            response = self.session.get(f"{self.base_url}/history")
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"获取MeTube状态失败: {response.status_code}")
                return {"queue": [], "done": [], "pending": []}
                
        except Exception as e:
            logger.error(f"获取MeTube状态异常: {e}")
            return {"queue": [], "done": [], "pending": []}
    
    def check_connection(self) -> bool:
        """检查MeTube连接状态"""
        try:
            response = self.session.get(f"{self.base_url}/version", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"MeTube连接检查失败: {e}")
            return False

class URLValidator:
    """URL验证器"""
    
    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """从文本中提取URL"""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?]'
        urls = re.findall(url_pattern, text)
        return [url for url in urls if URLValidator.is_supported_url(url)]
    
    @staticmethod
    def is_supported_url(url: str) -> bool:
        """检查URL是否支持"""
        if not config.supported_domain_list:
            return True  # 如果没有配置限制，则支持所有URL
        
        for domain in config.supported_domain_list:
            if domain.lower() in url.lower():
                return True
        return False

class QywxMessageProcessor:
    """企业微信消息处理器"""
    
    def __init__(self):
        self._crypto = None
        self.message_sender = QywxMessageSender()
        self.metube_client = MeTubeClient()
        self.url_validator = URLValidator()
    
    def _get_crypto(self) -> WXBizMsgCrypt:
        """获取加密组件实例"""
        if self._crypto is None:
            if not all([config.sToken, config.sEncodingAESKey, config.sCorpID]):
                raise ValueError("企业微信配置不完整")
            
            self._crypto = WXBizMsgCrypt(
                config.sToken,
                config.sEncodingAESKey,
                config.sCorpID
            )
        return self._crypto
    
    def _parse_xml_message(self, xml_data: str) -> QywxMessage:
        """解析XML消息"""
        try:
            root = fromstring(xml_data)
            message_data = {node.tag: node.text for node in root}
            
            return QywxMessage(
                content=message_data.get('Content', ''),
                from_user=message_data.get('FromUserName', ''),
                to_user=message_data.get('ToUserName', ''),
                create_time=message_data.get('CreateTime', ''),
                msg_type=message_data.get('MsgType', ''),
                msg_id=message_data.get('MsgId', '')
            )
        except Exception as e:
            logger.error(f"解析XML消息失败: {e}")
            raise ValueError("消息格式错误")
    
    def _create_reply_xml(self, message: QywxMessage, content: str) -> str:
        """创建回复XML"""
        return XML_TEMPLATES["reply"].format(
            to_user=message.to_user,
            from_user=message.from_user,
            create_time=message.create_time,
            msg_type=message.msg_type,
            content=content,
            msg_id=message.msg_id,
            agent_id=config.sAgentid
        )
    
    def process_message(self, encrypted_msg: str, msg_signature: str, 
                       timestamp: str, nonce: str) -> str:
        """处理企业微信消息"""
        try:
            # 解密消息
            crypto = self._get_crypto()
            ret, decrypted_msg = crypto.DecryptMsg(
                encrypted_msg, msg_signature, timestamp, nonce
            )
            
            if ret != 0:
                logger.error(f"消息解密失败: {decrypted_msg}")
                raise ValueError("消息解密失败")
            
            # 解析消息
            message = self._parse_xml_message(decrypted_msg.decode('utf-8'))
            content = (message.content or "").strip()
            
            # 提取URL
            urls = self.url_validator.extract_urls(content)
            
            if not urls:
                reply_content = "❌ 未找到支持的视频链接\n\n支持的网站：YouTube、Bilibili等\n请发送有效的视频链接"
            else:
                # 异步处理下载任务
                self._process_download_async(message, urls)
                reply_content = f"✅ 已收到 {len(urls)} 个视频链接，正在提交下载..."
            
            # 创建回复XML
            reply_xml = self._create_reply_xml(message, reply_content)
            
            # 加密回复
            ret, encrypted_reply = crypto.EncryptMsg(reply_xml, nonce, timestamp)
            
            if ret != 0:
                logger.error(f"消息加密失败: {encrypted_reply}")
                raise ValueError("消息加密失败")
            
            return encrypted_reply
            
        except Exception as e:
            logger.error(f"处理企业微信消息失败: {e}")
            raise
    
    def _process_download_async(self, message: QywxMessage, urls: List[str]):
        """异步处理下载任务"""
        thread = DownloadProcessThread(message, urls)
        thread.start()

class DownloadProcessThread(threading.Thread):
    """下载处理线程"""
    
    def __init__(self, message: QywxMessage, urls: List[str]):
        super().__init__()
        self.name = "DownloadProcessThread"
        self.message = message
        self.urls = urls
        self.message_sender = QywxMessageSender()
        self.metube_client = MeTubeClient()
    
    def run(self):
        """线程执行方法"""
        try:
            results = []
            articles = []  # 存储图文消息的文章
            
            for url in self.urls:
                try:
                    # 提取视频信息
                    video_info = self.metube_client.youtube_extractor.extract_video_info(url)
                    
                    # 提交下载
                    result = self.metube_client.submit_download(url)
                    
                    if result.get('status') == 'ok':
                        # 添加到活跃任务列表进行监控
                        title = video_info.get('title', '正在获取标题...') if video_info.get('success') else "正在获取标题..."
                        download_monitor.add_active_task(url, self.message.from_user, title)
                        
                        # 获取视频标题用于显示
                        title = video_info.get('title', '视频') if video_info.get('success') else "视频"
                        results.append(f"✅ {title}\n已提交下载")
                        
                        # 如果成功提取视频信息，添加到图文消息
                        if video_info.get('success'):
                            article = {
                                'title': video_info.get('title', '未知标题'),
                                'description': f"上传者: {video_info.get('uploader', '未知')}\n时长: {self._format_duration(video_info.get('duration', 0))}\n观看次数: {video_info.get('view_count', 0):,}",
                                'url': url,
                                'picurl': video_info.get('thumbnail', '')
                            }
                            articles.append(article)
                    else:
                        error_msg = result.get('msg', '未知错误')
                        results.append(f"❌ {url}\n提交失败: {error_msg}")
                        logger.error(f"MeTube下载提交失败: {url}, 错误: {error_msg}")
                        
                except Exception as e:
                    logger.error(f"处理下载URL失败: {url}, 错误: {e}")
                    results.append(f"❌ {url}\n处理异常: {str(e)}")
            
            # 发送结果通知
            result_text = f"📥 下载任务提交结果：\n\n" + "\n\n".join(results)
            self.message_sender.send_text_message(result_text, self.message.from_user)
            
            # 如果有视频信息，发送图文消息
            if articles:
                try:
                    self.message_sender.send_news_message(articles, self.message.from_user)
                except Exception as e:
                    logger.error(f"发送图文消息失败: {e}")
            
        except Exception as e:
            logger.error(f"下载处理线程异常: {e}")
            error_msg = f"❌ 下载处理失败: {str(e)}"
            self.message_sender.send_text_message(error_msg, self.message.from_user)
    
    def _format_duration(self, duration: int) -> str:
        """格式化时长"""
        if duration == 0:
            return "未知"
        
        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"

class DownloadMonitor:
    """下载监控器"""
    
    def __init__(self):
        self.metube_client = MeTubeClient()
        self.message_sender = QywxMessageSender()
        self.last_check_time = datetime.datetime.now()
        self.active_tasks = {}  # 存储活跃的下载任务
    
    def calculate_next_check_interval(self, submit_time: datetime.datetime) -> int:
        """计算下次检查间隔（秒）"""
        elapsed_minutes = (datetime.datetime.now() - submit_time).total_seconds() / 60
        
        if elapsed_minutes < 3:
            return 10  # 前3分钟：每10秒检查一次
        elif elapsed_minutes < 10:
            return 60  # 3-10分钟：每1分钟检查一次
        elif elapsed_minutes < 50:
            return 300  # 10-50分钟：每5分钟检查一次
        elif elapsed_minutes < 120:
            return 600  # 50分钟-2小时：每10分钟检查一次
        elif elapsed_minutes < 4320:  # 72小时
            return 86400  # 2-72小时：每24小时检查一次
        else:
            return -1  # 72小时后不再检查
    
    async def check_downloads(self):
        """检查下载状态"""
        try:
            current_time = datetime.datetime.now()
            
            # 检查MeTube连接
            if not self.metube_client.check_connection():
                logger.debug("MeTube连接失败，跳过本次检查")
                return
            
            # 获取下载状态
            status = self.metube_client.get_download_status()
            
            # 处理活跃的下载任务
            await self._check_active_tasks(status)
            
            # 检查已完成的下载
            completed_downloads = status.get('done', [])
            await self._process_completed_downloads(completed_downloads)
            
            self.last_check_time = current_time
            logger.debug(f"下载状态检查完成，活跃任务: {len(self.active_tasks)}, 已完成下载: {len(completed_downloads)}")
            
        except Exception as e:
            logger.error(f"检查下载状态异常: {e}")
    
    async def _check_active_tasks(self, status: Dict[str, Any]):
        """检查活跃的下载任务"""
        current_time = datetime.datetime.now()
        tasks_to_remove = []
        
        for url, task in self.active_tasks.items():
            # 检查是否需要检查这个任务
            if task.last_check_time:
                elapsed_seconds = (current_time - task.last_check_time).total_seconds()
                if elapsed_seconds < task.next_check_interval:
                    continue
            
            # 更新检查时间
            task.last_check_time = current_time
            task.check_count += 1
            
            # 计算下次检查间隔
            next_interval = self.calculate_next_check_interval(task.submit_time)
            
            if next_interval == -1:
                # 超过72小时，停止检查
                logger.info(f"下载任务超过72小时未完成，停止检查: {url}")
                tasks_to_remove.append(url)
                continue
            
            task.next_check_interval = next_interval
            
            # 检查任务是否在MeTube的下载列表中
            found_in_queue = False
            for queue_item in status.get('queue', []):
                if queue_item.get('url') == url:
                    found_in_queue = True
                    break
            
            if not found_in_queue:
                # 任务不在队列中，可能已完成或失败
                logger.info(f"下载任务已不在队列中: {url}")
                tasks_to_remove.append(url)
        
        # 移除已完成或超时的任务
        for url in tasks_to_remove:
            del self.active_tasks[url]
    
    async def _process_completed_downloads(self, completed_downloads: List[Dict[str, Any]]):
        """处理已完成的下载"""
        if not completed_downloads:
            return
            
        logger.debug(f"检查已完成下载数量: {len(completed_downloads)}")
        processed_count = 0
        
        for download_item in completed_downloads:
            if download_item.get('status') != 'finished':
                continue
                
            url = download_item.get('url')
            if not url:
                continue
            
            # 检查是否已经处理过这个下载
            cache_key = f"processed_{url}"
            if processed_downloads_cache.get(cache_key):
                logger.debug(f"下载已完成且已处理过，跳过: {url}")
                continue
            
            logger.info(f"发现新的已完成下载: {url}")
            await self._process_completed_download(download_item)
            processed_count += 1
        
        if processed_count > 0:
            logger.info(f"本次处理了 {processed_count} 个新的已完成下载")
    
    async def _process_completed_download(self, download_item: Dict[str, Any]):
        """处理单个已完成的下载"""
        try:
            url = download_item.get('url')
            title = download_item.get('title', '未知标题')
            filename = download_item.get('filename')
            
            logger.info(f"处理下载完成: URL={url}, 标题={title}, 文件名={filename}")
            
            # 查找对应的下载任务
            download_task = None
            
            # 首先从活跃任务中查找
            if url in self.active_tasks:
                download_task = self.active_tasks[url]
                del self.active_tasks[url]
                logger.info(f"从活跃任务中找到下载任务: {url}")
            else:
                # 从缓存中查找
                download_task = download_cache.get(url)
                if download_task:
                    logger.info(f"从缓存中找到下载任务: {url}")
                else:
                    logger.warning(f"未找到下载任务记录: {url}")
            
            if not download_task:
                logger.warning(f"未找到下载任务记录，无法发送通知: {url}")
                # 检查是否应该为孤儿下载发送通知
                await self._handle_orphan_download(download_item)
                return
            
            # 检查是否已经通知过
            if download_task.status == 'completed':
                return
            
            # 构建下载链接
            if filename:
                # URL编码文件名
                import urllib.parse
                encoded_filename = urllib.parse.quote(filename)
                download_url = f"{config.metube_url}/download/{encoded_filename}"
            else:
                download_url = f"{config.metube_url}/download/"
            
            # 发送完成通知
            completion_message = f"""🎉 视频下载完成！

📹 标题：{title}
📁 文件：{filename or '未知'}
🔗 下载链接：{download_url}

点击链接即可下载文件"""
            
            logger.info(f"准备发送下载完成通知给用户: {download_task.user_id}")
            logger.info(f"通知内容: {completion_message}")
            
            success = self.message_sender.send_text_message(
                completion_message, 
                download_task.user_id
            )
            
            logger.info(f"下载完成通知发送结果: {success}")
            
            if success:
                # 更新任务状态
                download_task.status = 'completed'
                download_task.filename = filename
                download_task.download_url = download_url
                download_cache.set(url, download_task)
                
                # 标记为已处理，避免重复通知
                cache_key = f"processed_{url}"
                processed_downloads_cache.set(cache_key, {
                    'processed_time': datetime.datetime.now(),
                    'title': title,
                    'filename': filename,
                    'user_id': download_task.user_id
                })
                
                logger.info(f"下载完成通知已发送: {title}")
            else:
                logger.error(f"下载完成通知发送失败: {title}")
                
        except Exception as e:
            logger.error(f"处理完成下载异常: {e}")
    
    async def _handle_orphan_download(self, download_item: Dict[str, Any]):
        """处理孤儿下载（没有对应任务记录的已完成下载）"""
        try:
            url = download_item.get('url')
            title = download_item.get('title', '未知标题')
            filename = download_item.get('filename')
            
            logger.info(f"处理孤儿下载: {title}")
            
            # 检查是否已经处理过这个孤儿下载
            orphan_cache_key = f"orphan_{url}"
            if processed_downloads_cache.get(orphan_cache_key):
                logger.debug(f"孤儿下载已处理过: {url}")
                return
            
            # 构建下载链接
            if filename:
                import urllib.parse
                encoded_filename = urllib.parse.quote(filename)
                download_url = f"{config.metube_url}/download/{encoded_filename}"
            else:
                download_url = f"{config.metube_url}/download/"
            
            completion_message = f"""🎉 发现已完成下载！

📹 标题：{title}
📁 文件：{filename or '未知'}
🔗 下载链接：{download_url}

注意：此下载未通过企业微信提交，系统自动检测到完成状态。"""
            
            # 优先尝试发送给配置的孤儿下载用户
            notification_sent = False
            
            if config.notify_orphan_downloads and config.orphan_download_user:
                logger.info(f"准备发送孤儿下载通知给指定用户: {config.orphan_download_user}")
                success = self.message_sender.send_text_message(
                    completion_message, 
                    config.orphan_download_user
                )
                
                if success:
                    logger.info(f"孤儿下载通知发送成功: {title}")
                    notification_sent = True
                else:
                    logger.warning(f"孤儿下载通知发送失败: {title}")
            
            # 如果指定用户通知失败或未配置，则使用默认通道推送
            if not notification_sent:
                logger.info(f"尝试通过默认通道推送孤儿下载通知: {title}")
                
                # 获取默认通知配置
                default_route_id = getattr(config, 'default_route_id', None)
                default_channel = getattr(config, 'default_channel', None)
                default_target_type = getattr(config, 'default_target_type', 'router')
                
                logger.info(f"默认通知配置 - 类型: {default_target_type}, 路由ID: {default_route_id}, 频道: {default_channel}")
                
                # 使用插件自己的企业微信通道发送通知
                try:
                    logger.info(f"正在通过企业微信通道发送孤儿下载通知...")
                    
                    # 构建完整的通知消息
                    full_message = f"🎉 下载完成通知\n\n{completion_message}"
                    
                    # 使用插件自己的消息发送器发送到默认用户
                    default_user = getattr(config, 'default_user', None)
                    if default_user:
                        success = self.message_sender.send_text_message(full_message, default_user)
                        if success:
                            logger.info(f"通过企业微信通道发送孤儿下载通知成功: {title}")
                            notification_sent = True
                        else:
                            logger.error(f"通过企业微信通道发送孤儿下载通知失败: {title}")
                    else:
                        logger.warning(f"未配置默认用户，无法发送企业微信通知")
                        
                except Exception as e:
                    logger.error(f"通过企业微信通道发送孤儿下载通知异常: {e}")
                
                if not notification_sent:
                    logger.warning(f"所有通知方式均失败，孤儿下载通知未发送: {title}")
            
            # 标记为已处理
            processed_downloads_cache.set(orphan_cache_key, {
                'processed': True,
                'processed_time': datetime.datetime.now(),
                'title': title,
                'filename': filename,
                'download_url': download_url,
                'notification_sent': notification_sent
            })
            
        except Exception as e:
            logger.error(f"处理孤儿下载异常: {e}")
    
    def add_active_task(self, url: str, user_id: str, title: str = "获取中..."):
        """添加活跃下载任务"""
        download_task = DownloadTask(
            url=url,
            title=title,
            user_id=user_id,
            submit_time=datetime.datetime.now(),
            download_id=url,
            last_check_time=datetime.datetime.now(),
            check_count=0,
            next_check_interval=10
        )
        self.active_tasks[url] = download_task
        download_cache.set(url, download_task)
        logger.info(f"添加活跃下载任务: {url}")

class QywxCallbackHandler:
    """企业微信回调处理器"""
    
    def __init__(self):
        self._crypto = None
        self.message_processor = QywxMessageProcessor()
    
    def _get_crypto(self) -> WXBizMsgCrypt:
        """获取加密组件实例"""
        if self._crypto is None:
            if not all([config.sToken, config.sEncodingAESKey, config.sCorpID]):
                raise ValueError("企业微信配置不完整")
            
            self._crypto = WXBizMsgCrypt(
                config.sToken,
                config.sEncodingAESKey,
                config.sCorpID
            )
        return self._crypto
    
    def verify_url(self, msg_signature: str, timestamp: str, 
                   nonce: str, echostr: str) -> str:
        """验证回调URL"""
        try:
            crypto = self._get_crypto()
            ret, echo_str = crypto.VerifyURL(
                msg_signature, timestamp, nonce, echostr
            )
            
            if ret == 0:
                logger.info(f"企业微信URL验证成功")
                return echo_str.decode('utf-8')
            else:
                logger.error(f"企业微信URL验证失败: {echo_str}")
                raise ValueError("企业微信URL验证失败")
                
        except Exception as e:
            logger.error(f"企业微信URL验证异常: {e}")
            raise
    
    def handle_message(self, encrypted_msg: str, msg_signature: str,
                      timestamp: str, nonce: str) -> str:
        """处理接收到的消息"""
        return self.message_processor.process_message(
            encrypted_msg, msg_signature, timestamp, nonce
        )

# 全局实例
callback_handler = QywxCallbackHandler()
download_monitor = DownloadMonitor()

# 初始化钩子
@after_setup(plugin_id=PLUGIN_ID, desc="初始化下载监控器")
def setup_download_monitor():
    """设置下载监控器"""
    try:
        # 检查配置
        if not config.is_configured():
            logger.warning(f"{PLUGIN_NAME}: 配置不完整，请检查插件配置")
            return
        
        # 检查MeTube连接
        metube_client = MeTubeClient()
        if metube_client.check_connection():
            logger.info(f"{PLUGIN_NAME}: MeTube连接正常，开始监控下载")
        else:
            logger.warning(f"{PLUGIN_NAME}: MeTube连接失败，监控将在后台重试")
        
        # 注册定时任务，每5分钟检查一次下载状态
        def check_downloads_task():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(download_monitor.check_downloads())
                loop.close()
            except Exception as e:
                logger.error(f"下载监控任务执行失败: {e}")
        
        register_cron_job("*/5 * * * *", "检查MeTube下载状态", check_downloads_task)
        
    except Exception as e:
        logger.error(f"{PLUGIN_NAME}: 初始化失败: {e}")

# API路由
@wx_metube_router.get("/chat")
async def verify_callback(request: Request):
    """企业微信回调URL验证接口"""
    try:
        # 获取验证参数
        msg_signature = request.query_params.get('msg_signature')
        timestamp = request.query_params.get('timestamp')
        nonce = request.query_params.get('nonce')
        echostr = request.query_params.get('echostr')
        
        # 记录验证请求
        logger.info(f"企业微信URL验证请求: msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}")
        
        # 验证必要参数
        if not all([msg_signature, timestamp, nonce, echostr]):
            logger.error(f"缺少必要的验证参数: msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}, echostr={echostr}")
            raise HTTPException(status_code=400, detail="缺少必要的验证参数")
        
        # 执行验证
        try:
            result = callback_handler.verify_url(msg_signature, timestamp, nonce, echostr)
            logger.info(f"企业微信URL验证成功，返回: {result}")
            # 企业微信URL验证需要返回纯文本响应
            return Response(content=str(result), media_type="text/plain")
        except ValueError as e:
            logger.error(f"企业微信URL验证失败: {e}")
            raise HTTPException(status_code=500, detail=f"URL验证失败: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"企业微信回调验证异常: {e}", exc_info=True)
        return json_500("服务器内部错误")

@wx_metube_router.post("/chat")
async def receive_message(request: Request):
    """企业微信消息接收接口"""
    try:
        # 获取消息参数
        msg_signature = request.query_params.get('msg_signature')
        timestamp = request.query_params.get('timestamp')
        nonce = request.query_params.get('nonce')
        
        # 记录消息请求
        logger.info(f"企业微信消息接收请求: msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}")
        
        # 验证必要参数
        if not all([msg_signature, timestamp, nonce]):
            logger.error(f"缺少必要的消息参数: msg_signature={msg_signature}, timestamp={timestamp}, nonce={nonce}")
            raise HTTPException(status_code=400, detail="缺少必要的验证参数")
        
        # 获取请求体
        body = await request.body()
        encrypted_msg = body.decode('utf-8')
        logger.debug(f"接收到的加密消息: {encrypted_msg[:100]}...")  # 只记录前100个字符
        
        # 处理消息
        try:
            result = callback_handler.handle_message(
                encrypted_msg, msg_signature, timestamp, nonce
            )
            logger.info("企业微信消息处理成功")
            return Response(content=result, media_type="text/plain")
        except ValueError as e:
            logger.error(f"企业微信消息处理失败: {e}")
            raise HTTPException(status_code=500, detail=f"消息处理失败: {str(e)}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"企业微信消息处理异常: {e}", exc_info=True)
        return json_500("服务器内部错误")

@wx_metube_router.get("/status")
async def get_plugin_status():
    """获取插件状态"""
    try:
        metube_client = MeTubeClient()
        metube_online = metube_client.check_connection()
        
        # 获取下载统计
        download_stats = metube_client.get_download_status()
        queue_count = len(download_stats.get('queue', []))
        done_count = len(download_stats.get('done', []))
        
        # 获取活跃任务统计
        active_tasks = []
        for url, task in download_monitor.active_tasks.items():
            elapsed_minutes = (datetime.datetime.now() - task.submit_time).total_seconds() / 60
            active_tasks.append({
                "url": url,
                "title": task.title,
                "user_id": task.user_id,
                "submit_time": task.submit_time.isoformat(),
                "elapsed_minutes": round(elapsed_minutes, 1),
                "check_count": task.check_count,
                "next_check_interval": task.next_check_interval,
                "last_check_time": task.last_check_time.isoformat() if task.last_check_time else None
            })
        
        return {
            "plugin_name": PLUGIN_NAME,
            "metube_online": metube_online,
            "metube_url": config.metube_url,
            "queue_count": queue_count,
            "done_count": done_count,
            "active_tasks_count": len(download_monitor.active_tasks),
            "active_tasks": active_tasks,
            "last_check": download_monitor.last_check_time.isoformat(),
            "config_ok": config.is_configured()
        }
        
    except Exception as e:
        logger.error(f"获取插件状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取状态失败: {e}")

@wx_metube_router.post("/test-metube")
async def test_metube_connection():
    """测试MeTube连接"""
    try:
        metube_client = MeTubeClient()
        is_online = metube_client.check_connection()
        
        if is_online:
            # 获取版本信息
            try:
                import httpx
                response = httpx.get(f"{config.metube_url}/version", timeout=5)
                if response.status_code == 200:
                    version_info = response.json()
                    return {
                        "success": True,
                        "message": "MeTube连接正常",
                        "metube_url": config.metube_url,
                        "version_info": version_info
                    }
            except Exception as e:
                logger.warning(f"获取MeTube版本信息失败: {e}")
        
        return {
            "success": False,
            "message": "MeTube连接失败",
            "metube_url": config.metube_url
        }
        
    except Exception as e:
        logger.error(f"测试MeTube连接失败: {e}")
        raise HTTPException(status_code=500, detail=f"连接测试失败: {e}")

@wx_metube_router.post("/manual-check")
async def manual_check_downloads():
    """手动检查下载状态"""
    try:
        # 在当前事件循环中运行检查任务
        await download_monitor.check_downloads()
        return {
            "success": True,
            "message": "手动检查完成",
            "check_time": download_monitor.last_check_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"手动检查下载状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"手动检查失败: {e}")

@wx_metube_router.post("/reload-config")
async def reload_config():
    """重新加载配置"""
    try:
        config.reload()
        
        # 测试连接
        metube_client = MeTubeClient()
        metube_online = metube_client.check_connection()
        
        return {
            "success": True,
            "message": "配置重新加载成功",
            "metube_online": metube_online,
            "config_ok": config.is_configured()
        }
        
    except Exception as e:
        logger.error(f"重新加载配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {e}")

@wx_metube_router.get("/debug/callback")
async def debug_callback():
    """调试企业微信回调配置"""
    try:
        debug_info = {
            "plugin_id": PLUGIN_ID,
            "callback_url": f"/api/plugins/{PLUGIN_ID}/chat",
            "config_status": {
                "qywx_base_url": config.qywx_base_url,
                "sCorpID": config.sCorpID,
                "sCorpsecret": "***" if config.sCorpsecret else "",
                "sAgentid": config.sAgentid,
                "sToken": "***" if config.sToken else "",
                "sEncodingAESKey": "***" if config.sEncodingAESKey else "",
            },
            "config_complete": config.is_configured(),
            "crypto_available": False
        }
        
        # 检查加密组件是否可用
        try:
            from notifyhub.plugins.components.qywx_Crypt.WXBizMsgCrypt import WXBizMsgCrypt
            if all([config.sToken, config.sEncodingAESKey, config.sCorpID]):
                debug_info["crypto_available"] = True
        except Exception as e:
            debug_info["crypto_error"] = str(e)
        
        return debug_info
        
    except Exception as e:
        logger.error(f"调试信息获取失败: {e}")
        raise HTTPException(status_code=500, detail=f"调试信息获取失败: {e}")

@wx_metube_router.get("/images/{filename}")
async def get_cached_image(filename: str):
    """获取缓存的图片"""
    try:
        # 安全检查：只允许.jpg文件
        if not filename.endswith('.jpg'):
            raise HTTPException(status_code=400, detail="只支持jpg格式")
        
        image_path = IMAGE_CACHE_DIR / filename
        
        if not image_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")
        
        # 返回图片文件
        return Response(
            content=image_path.read_bytes(),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",  # 缓存1天
                "Content-Disposition": f"inline; filename={filename}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取缓存图片失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取图片失败: {e}")

@wx_metube_router.get("/orphan-downloads")
async def get_orphan_downloads():
    """获取孤儿下载状态"""
    try:
        orphan_downloads = []
        
        # 从缓存中获取孤儿下载记录
        for key in processed_downloads_cache.keys():
            if key.startswith('orphan_'):
                orphan_data = processed_downloads_cache.get(key)
                if orphan_data:
                    orphan_downloads.append({
                        'url': key.replace('orphan_', ''),
                        'title': orphan_data.get('title', '未知'),
                        'filename': orphan_data.get('filename', '未知'),
                        'download_url': orphan_data.get('download_url', ''),
                        'processed_time': orphan_data.get('processed_time', '').isoformat() if orphan_data.get('processed_time') else '',
                        'processed': orphan_data.get('processed', False)
                    })
        
        return {
            "orphan_downloads_count": len(orphan_downloads),
            "orphan_downloads": orphan_downloads,
            "notify_orphan_downloads": getattr(config, 'notify_orphan_downloads', False),
            "orphan_download_user": getattr(config, 'orphan_download_user', ''),
            "cache_size": len(processed_downloads_cache)
        }
        
    except Exception as e:
        logger.error(f"获取孤儿下载状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取孤儿下载状态失败: {e}")

@wx_metube_router.post("/clear-orphan-cache")
async def clear_orphan_cache():
    """清理孤儿下载缓存"""
    try:
        cleared_count = 0
        
        # 清理孤儿下载缓存
        keys_to_remove = []
        for key in processed_downloads_cache.keys():
            if key.startswith('orphan_'):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            processed_downloads_cache.delete(key)
            cleared_count += 1
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "message": f"已清理 {cleared_count} 个孤儿下载缓存记录"
        }
        
    except Exception as e:
        logger.error(f"清理孤儿下载缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理缓存失败: {e}")


@wx_metube_router.get("/processed-downloads")
async def get_processed_downloads():
    """获取已处理的下载记录"""
    try:
        processed_downloads = []
        
        # 从缓存中获取已处理的下载记录
        for key in processed_downloads_cache.keys():
            if key.startswith('processed_'):
                data = processed_downloads_cache.get(key)
                if data:
                    processed_downloads.append({
                        'url': key.replace('processed_', ''),
                        'processed_time': data.get('processed_time', '').isoformat() if data.get('processed_time') else '',
                        'title': data.get('title', '未知'),
                        'filename': data.get('filename', '未知'),
                        'user_id': data.get('user_id', '未知')
                    })
        
        return {
            "processed_downloads_count": len(processed_downloads),
            "processed_downloads": processed_downloads,
            "cache_size": len(processed_downloads_cache)
        }
        
    except Exception as e:
        logger.error(f"获取已处理下载记录失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取记录失败: {e}")


@wx_metube_router.post("/clear-processed-cache")
async def clear_processed_cache():
    """清理已处理下载缓存"""
    try:
        cleared_count = len(processed_downloads_cache)
        processed_downloads_cache.clear()
        
        return {
            "success": True,
            "cleared_count": cleared_count,
            "message": f"已清理 {cleared_count} 个已处理下载缓存记录"
        }
        
    except Exception as e:
        logger.error(f"清理已处理下载缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理缓存失败: {e}")
