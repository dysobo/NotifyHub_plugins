#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
立即创建所有插件Release的脚本
使用GitHub API直接创建Release
"""

import os
import json
import requests
import glob
from datetime import datetime

def get_github_token():
    """获取GitHub Token"""
    # 从环境变量获取token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("请在环境变量中设置GITHUB_TOKEN")
        print("或者手动输入GitHub Personal Access Token:")
        print("1. 访问: https://github.com/settings/tokens")
        print("2. 创建新的Personal Access Token")
        print("3. 设置权限: repo (Full control of private repositories)")
        token = input("GitHub Token: ").strip()
    return token

def get_plugin_info(plugin_dir):
    """获取插件信息"""
    manifest_path = f"{plugin_dir}/manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def create_release_with_api(token, tag_name, plugin_name, plugin_dir, zip_file):
    """使用GitHub API创建Release"""
    print(f"正在为 {plugin_name} 创建Release...")
    
    # 获取插件信息
    manifest = get_plugin_info(plugin_dir)
    version = manifest.get('version', '1.0.0') if manifest else '1.0.0'
    description = manifest.get('description', '无描述') if manifest else '无描述'
    author = manifest.get('author', '未知') if manifest else '未知'
    
    # API URL
    url = "https://api.github.com/repos/dysobo/NotifyHub_plugins/releases"
    
    # Headers
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # 检查Release是否已存在
    check_url = f"https://api.github.com/repos/dysobo/NotifyHub_plugins/releases/tags/{tag_name}"
    response = requests.get(check_url, headers=headers)
    if response.status_code == 200:
        print(f"Release {tag_name} 已存在，跳过")
        return True
    
    # 创建Release标题和描述
    title = f"{plugin_name} v{version}"
    body = f"""自动发布的 {plugin_name} 插件包

**插件信息:**
- 名称: {plugin_name}
- 版本: {version}
- 描述: {description}
- 作者: {author}

**更新时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**仓库地址:** https://github.com/dysobo/NotifyHub_plugins

**安装说明:**
1. 下载zip文件
2. 解压到NotifyHub的plugins目录
3. 重启NotifyHub服务
4. 在插件管理中启用插件

**注意事项:**
- 请确保NotifyHub版本兼容
- 安装前请备份现有配置
- 如有问题请提交Issue反馈"""
    
    # 创建Release数据
    release_data = {
        "tag_name": tag_name,
        "target_commitish": "main",
        "name": title,
        "body": body,
        "draft": False,
        "prerelease": False
    }
    
    # 创建Release
    response = requests.post(url, headers=headers, json=release_data)
    
    if response.status_code == 201:
        release_info = response.json()
        upload_url = release_info['upload_url'].split('{')[0]
        print(f"[SUCCESS] Release创建成功: {tag_name}")
        
        # 上传文件
        return upload_file(token, upload_url, zip_file, tag_name)
    else:
        print(f"[ERROR] 创建Release失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False

def upload_file(token, upload_url, zip_file, tag_name):
    """上传文件到Release"""
    filename = os.path.basename(zip_file)
    
    headers = {
        'Authorization': f'token {token}',
        'Content-Type': 'application/zip'
    }
    
    with open(zip_file, 'rb') as f:
        files = {'file': (filename, f, 'application/zip')}
        
        response = requests.post(
            f"{upload_url}?name={filename}&label={filename}",
            headers=headers,
            files=files
        )
    
    if response.status_code == 201:
        print(f"[SUCCESS] 文件上传成功: {filename}")
        return True
    else:
        print(f"[ERROR] 文件上传失败: {response.status_code}")
        print(f"错误信息: {response.text}")
        return False

def main():
    """主函数"""
    print("NotifyHub 插件立即发布工具")
    print("=" * 50)
    
    # 检查packages目录
    if not os.path.exists('packages'):
        print("[ERROR] 找不到packages目录，请先运行打包脚本")
        return
    
    # 获取GitHub Token
    token = get_github_token()
    if not token:
        print("[ERROR] 未提供GitHub Token")
        return
    
    # 插件映射表
    plugin_map = {
        "plugin-用药提醒-2025.10.12": ("pill_reminder", "用药提醒"),
        "plugin-插件管理器-2025.10.12": ("plugin_manager", "插件管理器"),
        "plugin-QQ群消息转发-2025.10.12": ("qq_bridge", "QQ群消息转发"),
        "plugin-群晖Chat群组Webhook转发-2025.10.12": ("syno_chat_webhook", "群晖Chat群组Webhook转发"),
        "plugin-企业微信MeTube下载器-2025.10.12": ("wx_metube", "企业微信MeTube下载器")
    }
    
    # 获取所有zip文件
    zip_files = glob.glob('packages/*.zip')
    if not zip_files:
        print("[ERROR] 找不到任何插件包文件")
        return
    
    print(f"找到 {len(zip_files)} 个插件包:")
    for zip_file in zip_files:
        print(f"  - {zip_file}")
    
    print("\n开始创建所有插件Release...")
    
    # 为每个插件创建Release
    success_count = 0
    total_count = len(plugin_map)
    
    for tag_name, (plugin_dir, plugin_name) in plugin_map.items():
        print(f"\n处理插件: {plugin_name}")
        
        # 查找对应的zip文件
        zip_file = None
        for zf in zip_files:
            if plugin_name in zf:
                zip_file = zf
                break
        
        # 如果没找到，尝试其他匹配方式
        if not zip_file:
            case_map = {
                "用药提醒": "用药提醒",
                "插件管理器": "插件管理器",
                "QQ群消息转发": "QQ群消息转发",
                "群晖Chat群组Webhook转发": "群晖Chat",
                "企业微信MeTube下载器": "企业微信"
            }
            
            search_name = case_map.get(plugin_name, plugin_name)
            for zf in zip_files:
                if search_name in zf:
                    zip_file = zf
                    break
        
        if zip_file:
            if create_release_with_api(token, tag_name, plugin_name, plugin_dir, zip_file):
                success_count += 1
        else:
            print(f"[ERROR] 找不到 {plugin_name} 的打包文件")
        
        print("-" * 30)
    
    # 总结
    print("=" * 50)
    print(f"发布完成: {success_count}/{total_count} 个插件发布成功")
    
    if success_count > 0:
        print("\n[SUCCESS] 插件发布完成!")
        print("查看所有Release: https://github.com/dysobo/NotifyHub_plugins/releases")
    else:
        print("\n[ERROR] 没有插件发布成功")

if __name__ == "__main__":
    main()
