#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动创建GitHub Release的脚本
使用GitHub API直接创建Release，不依赖GitHub CLI
"""

import os
import json
import requests
import glob
from datetime import datetime

def get_github_token():
    """获取GitHub Token"""
    # 从环境变量或用户输入获取token
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        print("请在环境变量中设置GITHUB_TOKEN，或手动输入:")
        token = input("GitHub Token: ").strip()
    return token

def create_release_with_api(token, plugin_name, zip_file):
    """使用GitHub API创建Release"""
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
    
    # API URL
    url = "https://api.github.com/repos/dysobo/NotifyHub_plugins/releases"
    
    # Headers
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    # 创建Release标题和描述
    title = f"{manifest.get('name', plugin_name)} v{version}" if manifest else f"{plugin_name} v{version}"
    description = f"""自动发布的 {plugin_name} 插件包

**插件信息:**
- 名称: {manifest.get('name', plugin_name) if manifest else plugin_name}
- 版本: {version}
- 描述: {manifest.get('description', '无描述') if manifest else '无描述'}
- 作者: {manifest.get('author', '未知') if manifest else '未知'}

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
        "body": description,
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
    print("NotifyHub 插件手动发布工具")
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
    
    # 获取所有zip文件
    zip_files = glob.glob('packages/*.zip')
    if not zip_files:
        print("[ERROR] 找不到任何插件包文件")
        return
    
    print(f"找到 {len(zip_files)} 个插件包:")
    for zip_file in zip_files:
        print(f"  - {zip_file}")
    
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
        if create_release_with_api(token, plugin_name, zip_file):
            success_count += 1
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
