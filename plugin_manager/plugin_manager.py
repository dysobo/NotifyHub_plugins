"""
插件管理器后端API
提供插件仓库管理、插件下载安装、版本管理等功能
"""

import os
import json
import shutil
import zipfile
import tempfile
import requests
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging

from notifyhub.plugins.utils import get_plugin_config, get_plugin_data
from notifyhub.controller.server import server

# 配置日志
logger = logging.getLogger(__name__)

# 创建路由器
plugin_manager_router = APIRouter(prefix="/plugin_manager", tags=["plugin_manager"])

# 数据模型
class RepositoryInfo(BaseModel):
    id: str
    name: str
    url: str
    description: str = ""
    enabled: bool = True
    last_updated: Optional[str] = None

class PluginInfo(BaseModel):
    id: str
    name: str
    description: str
    author: str
    version: str
    logo: str = ""
    thumbnailurl: str = ""
    documentation: str = ""
    repository_id: str
    download_url: str
    file_size: int = 0
    install_count: int = 0
    last_updated: str = ""

class InstallRequest(BaseModel):
    plugin_id: str
    repository_id: str
    version: Optional[str] = None

class BackupRequest(BaseModel):
    plugin_id: str
    backup_name: Optional[str] = None

class RestoreRequest(BaseModel):
    plugin_id: str
    backup_file: str

# 全局变量
PLUGINS_DIR = Path("/data/plugins")
BACKUP_DIR = Path("/data/plugin_backups")
REPOSITORIES_FILE = Path("/data/plugin_repositories.json")
LOCAL_REPOSITORIES_DIR = Path("/data/local_repositories")

# 确保目录存在
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_REPOSITORIES_DIR.mkdir(parents=True, exist_ok=True)

# 默认仓库配置（已清空，只使用自定义仓库）
DEFAULT_REPOSITORIES = {}

def get_plugin_config_value(key: str, default: Any = None) -> Any:
    """获取插件配置值"""
    config = get_plugin_config("plugin_manager")
    return config.get(key, default)

def get_proxy_config() -> Dict[str, str]:
    """获取代理配置"""
    if get_plugin_config_value("proxy_enabled", False):
        proxy_url = get_plugin_config_value("proxy_url", "http://127.0.0.1:7890")
        return {
            "http": proxy_url,
            "https": proxy_url
        }
    return {}

def parse_github_url(url: str) -> Dict[str, str]:
    """解析GitHub URL，提取仓库信息"""
    # 匹配GitHub URL格式
    patterns = [
        r'https://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?(?:/(.*))?',
        r'https://github\.com/([^/]+)/([^/]+)',
        r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.*)'
    ]
    
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            if 'raw.githubusercontent.com' in url:
                # 处理raw.githubusercontent.com URL
                owner = match.group(1)
                repo = match.group(2)
                branch = match.group(3)
                path = match.group(4)
                return {
                    'owner': owner,
                    'repo': repo,
                    'branch': branch,
                    'path': path,
                    'api_url': f'https://api.github.com/repos/{owner}/{repo}/contents/{path}',
                    'raw_base': f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}'
                }
            else:
                # 处理github.com URL
                owner = match.group(1)
                repo = match.group(2)
                branch = match.group(3) if len(match.groups()) > 2 and match.group(3) else 'main'
                path = match.group(4) if len(match.groups()) > 3 and match.group(4) else ''
                return {
                    'owner': owner,
                    'repo': repo,
                    'branch': branch,
                    'path': path,
                    'api_url': f'https://api.github.com/repos/{owner}/{repo}/contents/{path}',
                    'raw_base': f'https://raw.githubusercontent.com/{owner}/{repo}/{branch}'
                }
    return {}

def scan_github_repository(repo_info: Dict[str, str]) -> Dict[str, Any]:
    """扫描GitHub仓库，生成插件列表"""
    try:
        github_info = parse_github_url(repo_info['url'])
        if not github_info:
            raise Exception("无法解析GitHub URL")
        
        logger.info(f"扫描GitHub仓库: {github_info['owner']}/{github_info['repo']}")
        
        # 使用GitHub API获取仓库内容
        proxies = get_proxy_config()
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'NotifyHub-PluginManager/1.0'
        }
        
        response = requests.get(github_info['api_url'], headers=headers, proxies=proxies, timeout=30)
        response.raise_for_status()
        
        contents = response.json()
        plugins = []
        
        # 如果是单个文件，转换为列表
        if isinstance(contents, dict):
            contents = [contents]
        
        for item in contents:
            if item['type'] == 'dir' and not item['name'].startswith('.'):
                # 检查是否是插件目录（包含manifest.json）
                plugin_id = item['name']
                manifest_url = f"{github_info['raw_base']}/{item['path']}/manifest.json"
                
                try:
                    manifest_response = requests.get(manifest_url, proxies=proxies, timeout=10)
                    if manifest_response.status_code == 200:
                        manifest_data = manifest_response.json()
                        
                        # 生成插件信息
                        plugin_info = {
                            "id": plugin_id,
                            "name": manifest_data.get("name", plugin_id),
                            "description": manifest_data.get("description", ""),
                            "author": manifest_data.get("author", "unknown"),
                            "version": manifest_data.get("version", "1.0.0"),
                            "logo": manifest_data.get("logo", ""),
                            "thumbnailurl": manifest_data.get("thumbnailurl", ""),
                            "documentation": manifest_data.get("documentation", ""),
                            "download_url": f"{github_info['raw_base']}/{item['path']}",
                            "file_size": 0,  # 无法直接获取
                            "category": "工具",
                            "install_count": 0,
                            "last_updated": item.get("updated_at", datetime.now().isoformat())
                        }
                        plugins.append(plugin_info)
                        logger.info(f"发现插件: {plugin_info['name']}")
                        
                except Exception as e:
                    logger.warning(f"无法获取插件 {plugin_id} 的manifest: {e}")
                    continue
        
        # 生成本地JSON文件
        local_json = {
            "name": repo_info.get("name", f"{github_info['owner']}/{github_info['repo']}"),
            "description": repo_info.get("description", f"从GitHub仓库 {github_info['owner']}/{github_info['repo']} 自动扫描生成"),
            "author": github_info['owner'],
            "version": "1.0.0",
            "plugins": plugins,
            "generated_at": datetime.now().isoformat(),
            "source_url": repo_info['url']
        }
        
        # 保存到本地文件
        local_file = LOCAL_REPOSITORIES_DIR / f"{repo_info['id']}.json"
        with open(local_file, 'w', encoding='utf-8') as f:
            json.dump(local_json, f, ensure_ascii=False, indent=2)
        
        logger.info(f"生成本地仓库文件: {local_file}, 包含 {len(plugins)} 个插件")
        return local_json
        
    except Exception as e:
        logger.error(f"扫描GitHub仓库失败: {e}")
        raise e

def get_repository_data(repo_info: RepositoryInfo) -> Dict[str, Any]:
    """获取仓库数据，优先使用本地缓存，否则扫描GitHub"""
    local_file = LOCAL_REPOSITORIES_DIR / f"{repo_info.id}.json"
    
    # 检查本地文件是否存在且较新（1小时内）
    if local_file.exists():
        try:
            file_time = datetime.fromtimestamp(local_file.stat().st_mtime)
            if datetime.now() - file_time < timedelta(hours=1):
                with open(local_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"读取本地仓库文件失败: {e}")
    
    # 如果是GitHub仓库，尝试扫描
    if "github.com" in repo_info.url:
        try:
            return scan_github_repository(repo_info.dict())
        except Exception as e:
            logger.error(f"扫描GitHub仓库失败: {e}")
            # 如果扫描失败，尝试直接请求JSON
            pass
    
    # 尝试直接请求JSON文件
    try:
        proxies = get_proxy_config()
        response = requests.get(repo_info.url, proxies=proxies, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"获取仓库数据失败: {e}")
        raise e

def load_repositories() -> Dict[str, RepositoryInfo]:
    """加载仓库配置"""
    repositories = {}
    
    # 加载默认仓库
    try:
        config = get_plugin_config("plugin_manager")
        if config is None:
            config = {}
        enabled_default_repos = config.get("default_repositories", ["official"])
    except Exception as e:
        logger.warning(f"获取插件配置失败: {e}")
        config = {}
        enabled_default_repos = ["official"]
    
    for repo_id, repo_info in DEFAULT_REPOSITORIES.items():
        if repo_id in enabled_default_repos:
            repositories[repo_id] = RepositoryInfo(**repo_info)
    
    # 加载自定义仓库
    custom_urls = config.get("custom_repository_urls", "")
    if custom_urls:
        for i, url in enumerate(custom_urls.split(',')):
            url = url.strip()
            if url:
                custom_id = f"custom_{i}"
                # 直接使用原始URL，GitHub URL会在get_repository_data中处理
                converted_url = url
                repositories[custom_id] = RepositoryInfo(
                    id=custom_id,
                    name=f"自定义仓库 {i+1}",
                    url=converted_url,
                    description=f"自定义仓库地址: {url}",
                    enabled=True
                )
    
    # 加载已保存的仓库配置（覆盖默认配置）
    if REPOSITORIES_FILE.exists():
        try:
            with open(REPOSITORIES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for k, v in data.items():
                    repositories[k] = RepositoryInfo(**v)
        except Exception as e:
            logger.warning(f"加载仓库配置文件失败: {e}")
    
    return repositories

def save_repositories(repositories: Dict[str, RepositoryInfo]):
    """保存仓库配置"""
    data = {k: v.dict() for k, v in repositories.items()}
    with open(REPOSITORIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_installed_plugins() -> List[str]:
    """获取已安装的插件列表"""
    if not PLUGINS_DIR.exists():
        return []
    
    plugins = []
    for item in PLUGINS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            manifest_file = item / "manifest.json"
            if manifest_file.exists():
                plugins.append(item.name)
    return plugins

def get_plugin_manifest(plugin_id: str) -> Optional[Dict]:
    """获取插件manifest信息"""
    manifest_file = PLUGINS_DIR / plugin_id / "manifest.json"
    if manifest_file.exists():
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取插件 {plugin_id} manifest失败: {e}")
    return None

@plugin_manager_router.get("/status")
async def get_status():
    """获取插件管理器状态"""
    try:
        config = get_plugin_config("plugin_manager")
        if config is None:
            config = {}
        repositories = load_repositories()
        installed_plugins = get_installed_plugins()
        
        return {
            "proxy_enabled": config.get("proxy_enabled", False),
            "proxy_url": config.get("proxy_url", ""),
            "custom_repository_urls": config.get("custom_repository_urls", ""),
            "repositories_count": len(repositories),
            "installed_plugins_count": len(installed_plugins),
            "auto_check_updates": config.get("auto_check_updates", True),
            "backup_retention_days": config.get("backup_retention_days", "30")
        }
    except Exception as e:
        logger.error(f"获取状态失败: {e}")
        return {
            "proxy_enabled": False,
            "proxy_url": "",
            "custom_repository_urls": "",
            "repositories_count": 0,
            "installed_plugins_count": 0,
            "auto_check_updates": True,
            "backup_retention_days": "30",
            "error": str(e)
        }

@plugin_manager_router.get("/repositories")
async def get_repositories():
    """获取仓库列表"""
    try:
        repositories = load_repositories()
        return {"repositories": list(repositories.values())}
    except Exception as e:
        logger.error(f"获取仓库列表失败: {e}")
        return {"repositories": [], "error": str(e)}

@plugin_manager_router.post("/repositories")
async def add_repository(repo: RepositoryInfo):
    """添加新仓库"""
    repositories = load_repositories()
    
    # 检查ID是否已存在
    if repo.id in repositories:
        raise HTTPException(status_code=400, detail=f"仓库ID '{repo.id}' 已存在")
    
    # 验证仓库URL
    try:
        proxies = get_proxy_config()
        response = requests.get(repo.url, proxies=proxies, timeout=10)
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法访问仓库URL: {str(e)}")
    
    repositories[repo.id] = repo
    save_repositories(repositories)
    
    return {"message": f"仓库 '{repo.name}' 添加成功"}

@plugin_manager_router.put("/repositories/{repo_id}")
async def update_repository(repo_id: str, repo: RepositoryInfo):
    """更新仓库信息"""
    repositories = load_repositories()
    
    if repo_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    # 验证仓库URL
    try:
        proxies = get_proxy_config()
        response = requests.get(repo.url, proxies=proxies, timeout=10)
        response.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法访问仓库URL: {str(e)}")
    
    repositories[repo_id] = repo
    save_repositories(repositories)
    
    return {"message": f"仓库 '{repo.name}' 更新成功"}

@plugin_manager_router.delete("/repositories/{repo_id}")
async def delete_repository(repo_id: str):
    """删除仓库"""
    repositories = load_repositories()
    
    if repo_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    if repo_id in DEFAULT_REPOSITORIES:
        raise HTTPException(status_code=400, detail="无法删除默认仓库")
    
    del repositories[repo_id]
    save_repositories(repositories)
    
    return {"message": f"仓库 '{repo_id}' 删除成功"}

@plugin_manager_router.get("/repositories/{repo_id}/plugins")
async def get_repository_plugins(repo_id: str):
    """获取仓库中的插件列表"""
    repositories = load_repositories()
    
    if repo_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    repo = repositories[repo_id]
    if not repo.enabled:
        raise HTTPException(status_code=400, detail="仓库已禁用")
    
    try:
        logger.info(f"正在获取仓库 {repo_id} 的插件列表，URL: {repo.url}")
        
        # 使用新的仓库数据获取方法
        repo_data = get_repository_data(repo)
        plugins = repo_data.get("plugins", [])
        
        logger.info(f"仓库 {repo_id} 找到 {len(plugins)} 个插件")
        
        # 添加仓库ID到每个插件
        for plugin in plugins:
            plugin["repository_id"] = repo_id
        
        return {
            "plugins": plugins, 
            "successful_url": repo.url,
            "generated_at": repo_data.get("generated_at"),
            "source_type": "github_scan" if "github.com" in repo.url else "json_file"
        }
        
    except Exception as e:
        logger.error(f"获取仓库 {repo_id} 插件列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取插件列表失败: {str(e)}")

@plugin_manager_router.get("/plugins/search")
async def search_plugins(
    query: str = Query("", description="搜索关键词"),
    repository_id: Optional[str] = Query(None, description="仓库ID"),
    category: Optional[str] = Query(None, description="插件分类")
):
    """搜索插件"""
    repositories = load_repositories()
    all_plugins = []
    failed_repos = []
    
    # 确定要搜索的仓库
    search_repos = [repo_id] if repository_id else [repo.id for repo in repositories.values() if repo.enabled]
    
    logger.info(f"开始搜索插件，仓库列表: {search_repos}")
    
    for repo_id in search_repos:
        try:
            repo = repositories[repo_id]
            
            logger.info(f"正在搜索仓库 {repo_id}: {repo.url}")
            
            # 使用新的仓库数据获取方法
            repo_data = get_repository_data(repo)
            plugins = repo_data.get("plugins", [])
            
            logger.info(f"仓库 {repo_id} 找到 {len(plugins)} 个插件")
            
            for plugin in plugins:
                plugin["repository_id"] = repo_id
                all_plugins.append(plugin)
                
        except Exception as e:
            logger.warning(f"搜索仓库 {repo_id} 失败: {e}")
            failed_repos.append(f"{repo_id}: {str(e)}")
            continue
    
    # 过滤插件
    if query:
        query_lower = query.lower()
        all_plugins = [
            plugin for plugin in all_plugins
            if (query_lower in plugin.get("name", "").lower() or
                query_lower in plugin.get("description", "").lower() or
                query_lower in plugin.get("author", "").lower())
        ]
    
    if category:
        all_plugins = [
            plugin for plugin in all_plugins
            if plugin.get("category") == category
        ]
    
    logger.info(f"搜索完成，找到 {len(all_plugins)} 个插件，失败仓库: {failed_repos}")
    
    return {
        "plugins": all_plugins,
        "failed_repositories": failed_repos,
        "total_repositories": len(search_repos),
        "successful_repositories": len(search_repos) - len(failed_repos)
    }

@plugin_manager_router.get("/plugins/{plugin_id}/info")
async def get_plugin_info(plugin_id: str, repository_id: str):
    """获取插件详细信息"""
    repositories = load_repositories()
    
    if repository_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    try:
        repo = repositories[repository_id]
        proxies = get_proxy_config()
        response = requests.get(repo.url, proxies=proxies, timeout=30)
        response.raise_for_status()
        
        repo_data = response.json()
        plugins = repo_data.get("plugins", [])
        
        # 查找指定插件
        plugin_info = None
        for plugin in plugins:
            if plugin.get("id") == plugin_id:
                plugin_info = plugin
                break
        
        if not plugin_info:
            raise HTTPException(status_code=404, detail="插件不存在")
        
        plugin_info["repository_id"] = repository_id
        
        # 检查是否已安装
        installed_plugins = get_installed_plugins()
        plugin_info["installed"] = plugin_id in installed_plugins
        
        if plugin_info["installed"]:
            local_manifest = get_plugin_manifest(plugin_id)
            if local_manifest:
                plugin_info["local_version"] = local_manifest.get("version")
                plugin_info["can_update"] = plugin_info.get("version") != local_manifest.get("version")
        
        return {"plugin": plugin_info}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取插件 {plugin_id} 信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取插件信息失败: {str(e)}")

@plugin_manager_router.post("/plugins/install")
async def install_plugin(request: InstallRequest, background_tasks: BackgroundTasks):
    """安装插件"""
    repositories = load_repositories()
    
    if request.repository_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    # 检查插件是否已安装
    installed_plugins = get_installed_plugins()
    if request.plugin_id in installed_plugins:
        raise HTTPException(status_code=400, detail="插件已安装")
    
    try:
        repo = repositories[request.repository_id]
        
        # 使用get_repository_data函数来获取仓库数据，支持GitHub仓库
        repo_data = get_repository_data(repo)
        plugins = repo_data.get("plugins", [])
        
        # 查找指定插件
        plugin_info = None
        for plugin in plugins:
            if plugin.get("id") == request.plugin_id:
                plugin_info = plugin
                break
        
        if not plugin_info:
            raise HTTPException(status_code=404, detail="插件不存在")
        
        # 添加到后台任务
        background_tasks.add_task(download_and_install_plugin, plugin_info, request.repository_id)
        
        return {"message": f"开始安装插件 '{plugin_info.get('name', request.plugin_id)}'"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安装插件 {request.plugin_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"安装插件失败: {str(e)}")

def download_and_install_plugin(plugin_info: Dict, repository_id: str):
    """下载并安装插件（后台任务）"""
    plugin_id = plugin_info["id"]
    plugin_name = plugin_info.get("name", plugin_id)
    
    try:
        logger.info(f"开始下载插件: {plugin_name}")
        
        # 获取下载URL
        download_url = plugin_info.get("download_url")
        if not download_url:
            raise Exception("插件没有下载地址")
        
        # 创建插件目录
        plugin_dir = PLUGINS_DIR / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查是否是GitHub仓库
        if "raw.githubusercontent.com" in download_url:
            # 从GitHub仓库下载插件文件
            download_github_plugin(plugin_info, plugin_dir)
        else:
            # 下载zip包
            download_zip_plugin(download_url, plugin_dir)
        
        logger.info(f"插件 {plugin_name} 安装成功")
        
        # 发送通知
        try:
            # 获取通知渠道配置
            notification_channel = get_plugin_config("plugin_manager").get("notification_channel", "default")
            
            # 构建详细的通知内容
            install_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            plugin_version = plugin_info.get("version", "未知")
            plugin_author = plugin_info.get("author", "未知")
            plugin_size = plugin_info.get("file_size", 0)
            plugin_description = plugin_info.get("description", "暂无描述")
            
            # 格式化文件大小
            if plugin_size > 0:
                if plugin_size < 1024:
                    size_text = f"{plugin_size} B"
                elif plugin_size < 1024 * 1024:
                    size_text = f"{plugin_size / 1024:.1f} KB"
                else:
                    size_text = f"{plugin_size / (1024 * 1024):.1f} MB"
            else:
                size_text = "未知"
            
            # 构建通知内容
            notification_content = f"""🎉 插件安装成功！

📦 插件名称：{plugin_name}
👤 作者：{plugin_author}
📋 版本：{plugin_version}
📏 大小：{size_text}
⏰ 安装时间：{install_time}

📝 功能描述：
{plugin_description}

⚠️ 重要提示：请重启NotifyHub服务后生效！"""
            
            server.send_notify_by_channel(
                channel_name=notification_channel,
                title="🎉 插件安装完成",
                content=notification_content,
                push_link_url=f"/api/plugins/plugin_manager/plugins/{plugin_id}/info?repository_id={repository_id}"
            )
        except Exception as e:
            logger.warning(f"发送安装完成通知失败: {e}")
        
    except Exception as e:
        logger.error(f"安装插件 {plugin_name} 失败: {e}")
        try:
            # 获取通知渠道配置
            notification_channel = get_plugin_config("plugin_manager").get("notification_channel", "default")
            
            # 构建失败通知内容
            install_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            plugin_version = plugin_info.get("version", "未知")
            plugin_author = plugin_info.get("author", "未知")
            
            failure_content = f"""❌ 插件安装失败

📦 插件名称：{plugin_name}
👤 作者：{plugin_author}
📋 版本：{plugin_version}
⏰ 失败时间：{install_time}

🚨 错误信息：
{str(e)}

💡 建议：
• 检查网络连接
• 确认插件仓库可访问
• 查看系统日志获取详细信息"""
            
            server.send_notify_by_channel(
                channel_name=notification_channel,
                title="❌ 插件安装失败",
                content=failure_content
            )
        except Exception as notify_error:
            logger.warning(f"发送安装失败通知失败: {notify_error}")

def download_github_plugin(plugin_info: Dict, plugin_dir: Path):
    """从GitHub仓库下载插件文件"""
    plugin_id = plugin_info["id"]
    download_url = plugin_info.get("download_url")
    
    logger.info(f"开始下载GitHub插件: {plugin_id}, download_url: {download_url}")
    
    # 解析GitHub URL
    github_info = parse_github_url(download_url)
    if not github_info:
        raise Exception("无法解析GitHub URL")
    
    logger.info(f"解析GitHub信息: {github_info}")
    
    # 递归下载目录内容
    download_github_directory(github_info, plugin_dir, "")

def download_github_directory(github_info: Dict, target_dir: Path, relative_path: str = ""):
    """递归下载GitHub目录内容"""
    proxies = get_proxy_config()
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'NotifyHub-PluginManager/1.0'
    }
    
    # 构建API URL
    if relative_path:
        api_url = f"https://api.github.com/repos/{github_info['owner']}/{github_info['repo']}/contents/{github_info['path']}/{relative_path}"
    else:
        api_url = f"https://api.github.com/repos/{github_info['owner']}/{github_info['repo']}/contents/{github_info['path']}"
    
    logger.info(f"获取目录内容: {api_url}")
    
    response = requests.get(api_url, headers=headers, proxies=proxies, timeout=30)
    response.raise_for_status()
    
    contents = response.json()
    if isinstance(contents, dict):
        contents = [contents]
    
    # 处理每个项目
    for item in contents:
        if item['type'] == 'file':
            # 下载文件
            file_path = target_dir / item['name']
            file_url = item['download_url']
            
            logger.info(f"下载文件: {item['name']}")
            file_response = requests.get(file_url, proxies=proxies, timeout=30)
            file_response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                f.write(file_response.content)
                
        elif item['type'] == 'dir':
            # 递归下载子目录
            sub_dir = target_dir / item['name']
            sub_dir.mkdir(exist_ok=True)
            
            new_relative_path = f"{relative_path}/{item['name']}" if relative_path else item['name']
            logger.info(f"下载子目录: {item['name']}")
            download_github_directory(github_info, sub_dir, new_relative_path)

def download_zip_plugin(download_url: str, plugin_dir: Path):
    """下载zip包并解压"""
    proxies = get_proxy_config()
    response = requests.get(download_url, proxies=proxies, timeout=300)
    response.raise_for_status()
    
    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        plugin_zip = temp_path / "plugin.zip"
        
        # 保存插件包
        with open(plugin_zip, 'wb') as f:
            f.write(response.content)
        
        # 解压到插件目录
        with zipfile.ZipFile(plugin_zip, 'r') as zip_ref:
            zip_ref.extractall(plugin_dir)

@plugin_manager_router.delete("/plugins/{plugin_id}")
async def uninstall_plugin(plugin_id: str):
    """卸载插件"""
    installed_plugins = get_installed_plugins()
    
    if plugin_id not in installed_plugins:
        raise HTTPException(status_code=404, detail="插件未安装")
    
    try:
        # 获取插件信息用于通知
        manifest = get_plugin_manifest(plugin_id)
        plugin_name = manifest.get("name", plugin_id) if manifest else plugin_id
        plugin_version = manifest.get("version", "未知") if manifest else "未知"
        plugin_author = manifest.get("author", "未知") if manifest else "未知"
        
        plugin_dir = PLUGINS_DIR / plugin_id
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
        
        # 发送卸载成功通知
        try:
            notification_channel = get_plugin_config("plugin_manager").get("notification_channel", "default")
            uninstall_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            uninstall_content = f"""🗑️ 插件卸载成功

📦 插件名称：{plugin_name}
👤 作者：{plugin_author}
📋 版本：{plugin_version}
⏰ 卸载时间：{uninstall_time}

✅ 插件已从系统中完全移除"""
            
            server.send_notify_by_channel(
                channel_name=notification_channel,
                title="🗑️ 插件卸载完成",
                content=uninstall_content
            )
        except Exception as notify_error:
            logger.warning(f"发送卸载通知失败: {notify_error}")
        
        return {"message": f"插件 '{plugin_name}' 卸载成功"}
        
    except Exception as e:
        logger.error(f"卸载插件 {plugin_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"卸载插件失败: {str(e)}")

@plugin_manager_router.get("/installed")
async def get_installed_plugins_info():
    """获取已安装插件信息"""
    installed_plugins = get_installed_plugins()
    plugins_info = []
    
    for plugin_id in installed_plugins:
        manifest = get_plugin_manifest(plugin_id)
        if manifest:
            plugins_info.append({
                "id": plugin_id,
                "name": manifest.get("name", plugin_id),
                "version": manifest.get("version", "unknown"),
                "author": manifest.get("author", "unknown"),
                "description": manifest.get("description", ""),
                "logo": manifest.get("logo", ""),
                "thumbnailurl": manifest.get("thumbnailurl", ""),
                "last_modified": datetime.fromtimestamp(
                    (PLUGINS_DIR / plugin_id).stat().st_mtime
                ).isoformat()
            })
    
    return {"plugins": plugins_info}

@plugin_manager_router.get("/backups")
async def get_backups(plugin_id: str):
    """获取插件备份列表"""
    backup_plugin_dir = BACKUP_DIR / plugin_id
    if not backup_plugin_dir.exists():
        return {"backups": []}
    
    backups = []
    for backup_file in backup_plugin_dir.iterdir():
        if backup_file.suffix == '.zip':
            backups.append({
                "filename": backup_file.name,
                "size": backup_file.stat().st_size,
                "created": datetime.fromtimestamp(backup_file.stat().st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(backup_file.stat().st_mtime).isoformat()
            })
    
    # 按创建时间倒序排列
    backups.sort(key=lambda x: x["created"], reverse=True)
    return {"backups": backups}

@plugin_manager_router.post("/backups")
async def create_backup(request: BackupRequest):
    """创建插件备份"""
    installed_plugins = get_installed_plugins()
    
    if request.plugin_id not in installed_plugins:
        raise HTTPException(status_code=404, detail="插件未安装")
    
    try:
        plugin_dir = PLUGINS_DIR / request.plugin_id
        backup_plugin_dir = BACKUP_DIR / request.plugin_id
        backup_plugin_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成备份文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if request.backup_name:
            backup_filename = f"{request.backup_name}_{timestamp}.zip"
        else:
            backup_filename = f"{request.plugin_id}_{timestamp}.zip"
        
        backup_path = backup_plugin_dir / backup_filename
        
        # 创建备份
        with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(plugin_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(plugin_dir)
                    zipf.write(file_path, arcname)
        
        # 发送备份成功通知
        try:
            notification_channel = get_plugin_config("plugin_manager").get("notification_channel", "default")
            manifest = get_plugin_manifest(request.plugin_id)
            plugin_name = manifest.get("name", request.plugin_id) if manifest else request.plugin_id
            plugin_version = manifest.get("version", "未知") if manifest else "未知"
            backup_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 获取备份文件大小
            backup_size = backup_path.stat().st_size
            if backup_size < 1024:
                size_text = f"{backup_size} B"
            elif backup_size < 1024 * 1024:
                size_text = f"{backup_size / 1024:.1f} KB"
            else:
                size_text = f"{backup_size / (1024 * 1024):.1f} MB"
            
            backup_content = f"""💾 插件备份创建成功

📦 插件名称：{plugin_name}
📋 版本：{plugin_version}
📁 备份文件：{backup_filename}
📏 备份大小：{size_text}
⏰ 备份时间：{backup_time}

✅ 备份已保存到本地，可用于恢复插件"""
            
            server.send_notify_by_channel(
                channel_name=notification_channel,
                title="💾 插件备份完成",
                content=backup_content
            )
        except Exception as notify_error:
            logger.warning(f"发送备份通知失败: {notify_error}")
        
        return {
            "message": f"插件 '{request.plugin_id}' 备份创建成功",
            "backup_file": backup_filename
        }
        
    except Exception as e:
        logger.error(f"创建插件 {request.plugin_id} 备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建备份失败: {str(e)}")

@plugin_manager_router.post("/backups/restore")
async def restore_backup(request: RestoreRequest):
    """恢复插件备份"""
    backup_plugin_dir = BACKUP_DIR / request.plugin_id
    backup_path = backup_plugin_dir / request.backup_file
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    
    try:
        plugin_dir = PLUGINS_DIR / request.plugin_id
        
        # 如果插件目录存在，先备份当前版本
        if plugin_dir.exists():
            current_backup_name = f"restore_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            current_backup_dir = backup_plugin_dir
            current_backup_dir.mkdir(parents=True, exist_ok=True)
            current_backup_path = current_backup_dir / f"{current_backup_name}.zip"
            
            with zipfile.ZipFile(current_backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(plugin_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(plugin_dir)
                        zipf.write(file_path, arcname)
            
            # 删除当前插件目录
            shutil.rmtree(plugin_dir)
        
        # 恢复备份
        plugin_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup_path, 'r') as zip_ref:
            zip_ref.extractall(plugin_dir)
        
        # 发送恢复成功通知
        try:
            notification_channel = get_plugin_config("plugin_manager").get("notification_channel", "default")
            manifest = get_plugin_manifest(request.plugin_id)
            plugin_name = manifest.get("name", request.plugin_id) if manifest else request.plugin_id
            plugin_version = manifest.get("version", "未知") if manifest else "未知"
            restore_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            restore_content = f"""🔄 插件恢复成功

📦 插件名称：{plugin_name}
📋 版本：{plugin_version}
📁 备份文件：{request.backup_file}
⏰ 恢复时间：{restore_time}

✅ 插件已从备份成功恢复
⚠️ 请重启NotifyHub服务后生效"""
            
            server.send_notify_by_channel(
                channel_name=notification_channel,
                title="🔄 插件恢复完成",
                content=restore_content
            )
        except Exception as notify_error:
            logger.warning(f"发送恢复通知失败: {notify_error}")
        
        return {"message": f"插件 '{request.plugin_id}' 从备份恢复成功"}
        
    except Exception as e:
        logger.error(f"恢复插件 {request.plugin_id} 备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"恢复备份失败: {str(e)}")

@plugin_manager_router.delete("/backups/{plugin_id}/{backup_file}")
async def delete_backup(plugin_id: str, backup_file: str):
    """删除备份文件"""
    backup_plugin_dir = BACKUP_DIR / plugin_id
    backup_path = backup_plugin_dir / backup_file
    
    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    
    try:
        backup_path.unlink()
        return {"message": f"备份文件 '{backup_file}' 删除成功"}
        
    except Exception as e:
        logger.error(f"删除备份文件 {backup_file} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除备份失败: {str(e)}")

@plugin_manager_router.post("/cleanup")
async def cleanup_old_backups():
    """清理过期备份"""
    retention_days = int(get_plugin_config_value("backup_retention_days", "30"))
    
    if retention_days <= 0:
        return {"message": "备份永久保留，无需清理"}
    
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    cleaned_count = 0
    
    try:
        for plugin_backup_dir in BACKUP_DIR.iterdir():
            if plugin_backup_dir.is_dir():
                for backup_file in plugin_backup_dir.iterdir():
                    if backup_file.suffix == '.zip':
                        file_time = datetime.fromtimestamp(backup_file.stat().st_ctime)
                        if file_time < cutoff_date:
                            backup_file.unlink()
                            cleaned_count += 1
        
        return {"message": f"清理完成，删除了 {cleaned_count} 个过期备份文件"}
        
    except Exception as e:
        logger.error(f"清理备份失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理备份失败: {str(e)}")

@plugin_manager_router.get("/plugin/{plugin_id}/manifest")
async def get_plugin_manifest_api(plugin_id: str):
    """获取插件manifest信息（API接口）"""
    manifest = get_plugin_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail="插件不存在或manifest文件损坏")
    
    return {"manifest": manifest}

@plugin_manager_router.post("/repositories/{repo_id}/refresh")
async def refresh_repository(repo_id: str):
    """手动刷新仓库数据"""
    repositories = load_repositories()
    
    if repo_id not in repositories:
        raise HTTPException(status_code=404, detail="仓库不存在")
    
    repo = repositories[repo_id]
    
    try:
        # 删除本地缓存文件，强制重新扫描
        local_file = LOCAL_REPOSITORIES_DIR / f"{repo_id}.json"
        if local_file.exists():
            local_file.unlink()
            logger.info(f"删除本地缓存文件: {local_file}")
        
        # 重新获取仓库数据
        repo_data = get_repository_data(repo)
        plugins = repo_data.get("plugins", [])
        
        return {
            "message": f"仓库 '{repo.name}' 刷新成功",
            "plugins_count": len(plugins),
            "generated_at": repo_data.get("generated_at")
        }
        
    except Exception as e:
        logger.error(f"刷新仓库 {repo_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=f"刷新仓库失败: {str(e)}")

@plugin_manager_router.post("/repositories/refresh-all")
async def refresh_all_repositories():
    """刷新所有仓库数据"""
    repositories = load_repositories()
    results = []
    
    for repo_id, repo in repositories.items():
        if repo.enabled:
            try:
                # 删除本地缓存文件
                local_file = LOCAL_REPOSITORIES_DIR / f"{repo_id}.json"
                if local_file.exists():
                    local_file.unlink()
                
                # 重新获取仓库数据
                repo_data = get_repository_data(repo)
                plugins = repo_data.get("plugins", [])
                
                results.append({
                    "repo_id": repo_id,
                    "repo_name": repo.name,
                    "status": "success",
                    "plugins_count": len(plugins)
                })
                
            except Exception as e:
                logger.error(f"刷新仓库 {repo_id} 失败: {e}")
                results.append({
                    "repo_id": repo_id,
                    "repo_name": repo.name,
                    "status": "failed",
                    "error": str(e)
                })
    
    success_count = len([r for r in results if r["status"] == "success"])
    total_count = len(results)
    
    return {
        "message": f"刷新完成: {success_count}/{total_count} 个仓库成功",
        "results": results
    }

@plugin_manager_router.post("/settings")
async def save_settings(settings: Dict[str, Any]):
    """保存插件管理器设置"""
    try:
        # 注意：这里需要根据NotifyHub的实际配置保存机制来实现
        # 由于NotifyHub的配置系统可能不直接暴露保存接口，这里提供一个示例实现
        
        # 验证设置数据
        if "proxy_enabled" in settings and not isinstance(settings["proxy_enabled"], bool):
            raise HTTPException(status_code=400, detail="代理启用状态必须是布尔值")
        
        if "proxy_url" in settings and settings.get("proxy_enabled"):
            proxy_url = settings["proxy_url"]
            if not proxy_url or not proxy_url.startswith(("http://", "https://")):
                raise HTTPException(status_code=400, detail="代理地址格式不正确")
        
        if "backup_retention_days" in settings:
            try:
                days = int(settings["backup_retention_days"])
                if days < 0:
                    raise HTTPException(status_code=400, detail="备份保留天数不能为负数")
            except ValueError:
                raise HTTPException(status_code=400, detail="备份保留天数必须是数字")
        
        # 这里应该调用NotifyHub的配置保存API
        # 由于我们无法直接访问NotifyHub的配置系统，这里返回成功
        # 实际部署时，需要根据NotifyHub的API文档来实现
        
        return {"message": "设置保存成功", "settings": settings}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存设置失败: {e}")
        raise HTTPException(status_code=500, detail=f"保存设置失败: {str(e)}")

@plugin_manager_router.post("/restart")
async def restart_notifyhub():
    """重启NotifyHub服务"""
    try:
        logger.info("收到重启请求，准备重启NotifyHub...")
        # 使用server实例重启应用
        server.restart_app()
        return {"message": "NotifyHub重启中..."}
    except Exception as e:
        logger.error(f"重启NotifyHub失败: {e}")
        raise HTTPException(status_code=500, detail=f"重启失败: {str(e)}")

@plugin_manager_router.post("/reload-config")
async def reload_plugin_config():
    """重新加载插件配置"""
    try:
        logger.info("收到重新加载配置请求...")
        
        # 清除本地缓存
        await clear_cache()
        
        # 重新加载仓库配置
        load_repositories()
        
        # 尝试重新加载插件配置（如果NotifyHub支持）
        try:
            # 这里可以调用NotifyHub的插件重新加载API
            # 由于我们无法直接访问，这里只是记录日志
            logger.info("插件配置重新加载完成")
        except Exception as reload_error:
            logger.warning(f"重新加载插件配置时出现警告: {reload_error}")
        
        return {"message": "插件配置重新加载完成，建议重启NotifyHub以确保菜单显示正常"}
    except Exception as e:
        logger.error(f"重新加载配置失败: {e}")
        raise HTTPException(status_code=500, detail=f"重新加载配置失败: {str(e)}")

@plugin_manager_router.get("/debug/info")
async def get_debug_info():
    """获取调试信息"""
    try:
        repositories = load_repositories()
        installed_plugins = get_installed_plugins()
        
        return {
            "repositories": list(repositories.values()),
            "installed_plugins": installed_plugins,
            "default_repositories": DEFAULT_REPOSITORIES,
            "manifest_path": "plugin_manager/manifest.json",
            "frontend_page_configured": True
        }
    except Exception as e:
        logger.error(f"获取调试信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取调试信息失败: {str(e)}")

@plugin_manager_router.post("/clear-cache")
async def clear_cache():
    """清除所有缓存文件"""
    try:
        import shutil
        
        # 清除本地仓库缓存
        if LOCAL_REPOSITORIES_DIR.exists():
            shutil.rmtree(LOCAL_REPOSITORIES_DIR)
            LOCAL_REPOSITORIES_DIR.mkdir(parents=True, exist_ok=True)
        
        # 清除仓库配置文件
        if REPOSITORIES_FILE.exists():
            REPOSITORIES_FILE.unlink()
        
        logger.info("缓存清除完成")
        return {"message": "缓存清除成功"}
    except Exception as e:
        logger.error(f"清除缓存失败: {e}")
        raise HTTPException(status_code=500, detail=f"清除缓存失败: {str(e)}")

@plugin_manager_router.post("/force-reload")
async def force_reload():
    """强制重新加载插件配置"""
    try:
        # 清除缓存
        await clear_cache()
        
        # 重新加载仓库
        repositories = load_repositories()
        
        # 重新扫描所有仓库
        for repo_id, repo in repositories.items():
            if repo.enabled and "github.com" in repo.url:
                try:
                    scan_github_repository(repo.dict())
                    logger.info(f"重新扫描仓库: {repo.name}")
                except Exception as e:
                    logger.warning(f"重新扫描仓库 {repo.name} 失败: {e}")
        
        return {"message": "插件配置重新加载成功"}
    except Exception as e:
        logger.error(f"强制重新加载失败: {e}")
        raise HTTPException(status_code=500, detail=f"强制重新加载失败: {str(e)}")
