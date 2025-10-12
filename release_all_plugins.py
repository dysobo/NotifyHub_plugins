#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotifyHub 插件发布脚本
自动创建GitHub Release并上传插件包
"""

import os
import subprocess
import json
import glob
from datetime import datetime

def run_command(cmd):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def check_gh_cli():
    """检查GitHub CLI是否已安装"""
    success, stdout, stderr = run_command("gh --version")
    return success

def get_plugin_info(plugin_name):
    """获取插件信息"""
    manifest_path = f"{plugin_name}/manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def create_release_for_plugin(plugin_name, zip_file):
    """为单个插件创建GitHub Release"""
    print(f"正在为 {plugin_name} 创建Release...")
    
    # 获取插件信息
    manifest = get_plugin_info(plugin_name)
    if not manifest:
        print(f"[ERROR] 无法获取 {plugin_name} 的manifest信息")
        return False
    
    # 创建版本标签
    version = manifest.get('version', '1.0.0')
    timestamp = datetime.now().strftime('%Y.%m.%d')
    tag_name = f"plugin-{plugin_name}-{timestamp}"
    
    # 创建Release标题和描述
    title = f"{manifest.get('name', plugin_name)} v{version}"
    description = f"""自动发布的 {plugin_name} 插件包

**插件信息:**
- 名称: {manifest.get('name', plugin_name)}
- 版本: {version}
- 描述: {manifest.get('description', '无描述')}
- 作者: {manifest.get('author', '未知')}

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
    
    # 创建GitHub Release
    cmd = f'gh release create "{tag_name}" "{zip_file}" --title "{title}" --notes "{description}"'
    success, stdout, stderr = run_command(cmd)
    
    if success:
        print(f"[SUCCESS] {plugin_name} 发布成功: {tag_name}")
        print(f"Release URL: https://github.com/dysobo/NotifyHub_plugins/releases/tag/{tag_name}")
        return True
    else:
        print(f"[ERROR] {plugin_name} 发布失败: {stderr}")
        return False

def main():
    """主函数"""
    print("NotifyHub 插件自动发布工具")
    print("=" * 50)
    
    # 检查GitHub CLI
    if not check_gh_cli():
        print("[ERROR] GitHub CLI (gh) 未安装或未配置")
        print("请安装: https://cli.github.com/")
        print("配置认证: gh auth login")
        return
    
    # 检查是否在正确的目录
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
        
        if create_release_for_plugin(plugin_name, zip_file):
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
