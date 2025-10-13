"""
企业微信MeTube插件工具模块
"""

import logging
from notifyhub.plugins.utils import get_plugin_config

logger = logging.getLogger(__name__)

class Config:
    """插件配置管理"""
    
    def __init__(self):
        self._config = get_plugin_config("wx_metube") or {}
        self._load_config()
    
    def _load_config(self):
        """加载配置项"""
        # 企业微信配置
        self.qywx_base_url = self._config.get('qywx_base_url', 'https://qyapi.weixin.qq.com')
        self.sCorpID = self._config.get('sCorpID', '')
        self.sCorpsecret = self._config.get('sCorpsecret', '')
        self.sAgentid = self._config.get('sAgentid', '')
        self.sToken = self._config.get('sToken', '')
        self.sEncodingAESKey = self._config.get('sEncodingAESKey', '')
        
        # MeTube配置
        self.metube_url = self._config.get('metube_url', 'http://192.168.0.88:8081').rstrip('/')
        
        # 下载配置
        self.default_quality = self._config.get('default_quality', 'best')
        self.default_format = self._config.get('default_format', 'any')
        self.auto_start = self._config.get('auto_start', True)
        
        # 其他配置
        self.proxy = self._config.get('proxy', '')
        self.supported_domains = self._config.get('supported_domains', 'youtube.com,youtu.be,bilibili.com')
        
        # 孤儿下载通知配置
        self.notify_orphan_downloads = self._config.get('notify_orphan_downloads', False)
        self.orphan_download_user = self._config.get('orphan_download_user', '')
        
        # 默认通知通道配置（用于孤儿下载通知失败时的备用方案）
        self.default_target_type = self._config.get('default_target_type', 'router')
        self.default_route_id = self._config.get('default_route_id', '')
        self.default_channel = self._config.get('default_channel', '')
        
        # 解析支持的域名
        if self.supported_domains:
            self.supported_domain_list = [domain.strip() for domain in self.supported_domains.split(',') if domain.strip()]
        else:
            self.supported_domain_list = []
    
    def reload(self):
        """重新加载配置"""
        self._config = get_plugin_config("wx_metube") or {}
        self._load_config()
        logger.info("插件配置已重新加载")
    
    def is_configured(self):
        """检查配置是否完整"""
        required_fields = [
            'sCorpID', 'sCorpsecret', 'sAgentid', 
            'sToken', 'sEncodingAESKey', 'metube_url'
        ]
        
        for field in required_fields:
            if not getattr(self, field, ''):
                logger.warning(f"配置不完整，缺少: {field}")
                return False
        
        return True
    
    def get_proxy_config(self):
        """获取代理配置"""
        if self.proxy:
            return {
                "http": self.proxy,
                "https": self.proxy
            }
        return {}

# 全局配置实例
config = Config()
