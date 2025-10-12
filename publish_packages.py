#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotifyHub 插件包发布脚本
使用GitHub API直接发布插件包到Releases
"""

import os
import json
import requests
import glob
import base64
from datetime import datetime
import time

def get_github_token():
    """获取GitHub Token"""
    # 从环境变量获取token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("[ERROR] 请设置GITHUB_TOKEN环境变量")
        print("获取Token: https://github.com/settings/tokens")
        print("设置环境变量: set GITHUB_TOKEN=your_token_here")
        return None
    return token

def create_release_via_api(token, plugin_name, zip_file):
    """使用GitHub API创建Release"""
    repo = "dysobo/NotifyHub_plugins"
    
    # 获取插件信息
    manifest_path = f"{plugin_name}/manifest.json"
    manifest = None
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
    
    # 创建版本标签
    version = manifest.get('version', '1.0.0') if manifest else '1.0.0'
    timestamp = datetime.now().strftime('%Y.%m.%d')
    tag_name = f"plugin-{plugin_name}-{timestamp}"
    
    # Release标题和描述
    title = f"{manifest.get('name', plugin_name)} v{version}" if manifest else f"{plugin_name} v{version}"
    description = f"""自动发布的 {plugin_name} 插件包

**插件信息:**
- 名称: {manifest.get('name', plugin_name) if manifest else plugin_name}
- 版本: {version}
- 描述: {manifest.get('description', '无描述') if manifest else '无描述'}
- 作者: {manifest.get('author', '未知') if manifest else '未知'}

**更新时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**仓库地址:** https://github.com/{repo}

**安装说明:**
1. 下载zip文件
2. 解压到NotifyHub的plugins目录
3. 重启NotifyHub服务
4. 在插件管理中启用插件

**注意事项:**
- 请确保NotifyHub版本兼容
- 安装前请备份现有配置
- 如有问题请提交Issue反馈"""
    
    # 创建Release
    release_data = {
        "tag_name": tag_name,
        "target_commitish": "main",
        "name": title,
        "body": description,
        "draft": False,
        "prerelease": False
    }
    
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    # 创建Release
    url = f"https://api.github.com/repos/{repo}/releases"
    response = requests.post(url, headers=headers, json=release_data)
    
    if response.status_code == 201:
        release_info = response.json()
        release_id = release_info['id']
        upload_url = release_info['upload_url'].split('{')[0]
        
        print(f"[SUCCESS] Release创建成功: {tag_name}")
        
        # 上传文件
        return upload_file(token, zip_file, upload_url, tag_name)
    else:
        print(f"[ERROR] Release创建失败: {response.status_code}")
        print(f"响应: {response.text}")
        return False

def upload_file(token, zip_file, upload_url, tag_name):
    """上传文件到Release"""
    filename = os.path.basename(zip_file)
    
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/zip"
    }
    
    # 读取文件内容
    with open(zip_file, 'rb') as f:
        file_content = f.read()
    
    # 上传文件
    upload_params = {"name": filename}
    url = f"{upload_url}?name={filename}"
    
    response = requests.post(url, headers=headers, data=file_content)
    
    if response.status_code == 201:
        print(f"[SUCCESS] 文件上传成功: {filename}")
        print(f"Release URL: https://github.com/dysobo/NotifyHub_plugins/releases/tag/{tag_name}")
        return True
    else:
        print(f"[ERROR] 文件上传失败: {response.status_code}")
        print(f"响应: {response.text}")
        return False

def main():
    """主函数"""
    print("NotifyHub 插件包发布工具")
    print("=" * 50)
    
    # 检查GitHub Token
    token = get_github_token()
    if not token:
        return
    
    # 检查插件包目录
    if not os.path.exists('packages'):
        print("[ERROR] 找不到packages目录，请先运行打包脚本")
        return
    
    # 获取所有zip文件
    zip_files = glob.glob('packages/*.zip')
    if not zip_files:
        print("[ERROR] 找不到任何插件包文件")
        return
    
    print(f"找到 {len(zip_files)} 个插件包:")
    for zip_file in zip_files:
        filename = os.path.basename(zip_file)
        size = os.path.getsize(zip_file)
        print(f"  - {filename} ({size} bytes)")
    
    # 确认发布
    confirm = input("\n是否继续发布所有插件? (y/N): ")
    if confirm.lower() != 'y':
        print("取消发布")
        return
    
    # 发布所有插件
    success_count = 0
    total_count = len(zip_files)
    
    for zip_file in zip_files:
        # 从文件名提取插件名
        filename = os.path.basename(zip_file)
        plugin_name = filename.split('_')[0]
        
        print(f"\n正在发布插件: {plugin_name}")
        print("-" * 30)
        
        if create_release_via_api(token, plugin_name, zip_file):
            success_count += 1
        
        # 避免API限制
        time.sleep(2)
    
    # 总结
    print("\n" + "=" * 50)
    print(f"发布完成: {success_count}/{total_count} 个插件发布成功")
    
    if success_count > 0:
        print("\n[SUCCESS] 插件发布完成!")
        print("查看所有Release: https://github.com/dysobo/NotifyHub_plugins/releases")
    else:
        print("\n[ERROR] 没有插件发布成功")

if __name__ == "__main__":
    main()
