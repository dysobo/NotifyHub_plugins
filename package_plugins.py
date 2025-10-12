#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NotifyHub 插件自动打包脚本
将仓库内的5个插件分别打包为zip文件
"""

import os
import json
import zipfile
import shutil
from datetime import datetime

def read_manifest(plugin_path):
    """读取插件的manifest.json文件"""
    manifest_path = os.path.join(plugin_path, 'manifest.json')
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def create_plugin_package(plugin_name, plugin_path, output_dir):
    """为单个插件创建打包文件"""
    print(f"正在打包插件: {plugin_name}")
    
    # 读取manifest信息
    manifest = read_manifest(plugin_path)
    if not manifest:
        print(f"警告: {plugin_name} 没有找到manifest.json文件")
        return False
    
    # 创建输出目录
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 确定包名
    package_name = manifest.get('name', plugin_name)
    version = manifest.get('version', '1.0.0')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 创建zip文件名
    zip_filename = f"{package_name}_v{version}_{timestamp}.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    
    # 创建zip文件
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # 添加所有插件文件
        for root, dirs, files in os.walk(plugin_path):
            # 排除一些不需要的文件
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', '.vscode']]
            
            for file in files:
                if file.endswith(('.pyc', '.pyo', '.log')):
                    continue
                
                file_path = os.path.join(root, file)
                arc_path = os.path.relpath(file_path, plugin_path)
                zipf.write(file_path, arc_path)
    
    print(f"[OK] 插件 {plugin_name} 打包完成: {zip_filename}")
    return True

def create_all_packages():
    """为所有插件创建打包文件"""
    plugins = [
        'pill_reminder',
        'plugin_manager', 
        'qq_bridge',
        'syno_chat_webhook',
        'wx_metube'
    ]
    
    output_dir = 'packages'
    success_count = 0
    
    print("开始打包NotifyHub插件...")
    print("=" * 50)
    
    for plugin in plugins:
        plugin_path = plugin
        if os.path.exists(plugin_path):
            if create_plugin_package(plugin, plugin_path, output_dir):
                success_count += 1
        else:
            print(f"[ERROR] 插件目录不存在: {plugin}")
    
    print("=" * 50)
    print(f"[INFO] 打包完成! 成功打包 {success_count}/{len(plugins)} 个插件")
    print(f"[INFO] 打包文件保存在: {output_dir}/")
    
    # 创建打包信息文件
    create_package_info(output_dir)
    
    return success_count == len(plugins)

def create_package_info(output_dir):
    """创建打包信息文件"""
    info_file = os.path.join(output_dir, 'PACKAGE_INFO.txt')
    
    with open(info_file, 'w', encoding='utf-8') as f:
        f.write("NotifyHub 插件打包信息\n")
        f.write("=" * 40 + "\n")
        f.write(f"打包时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"仓库地址: https://github.com/dysobo/NotifyHub_plugins\n")
        f.write("\n插件列表:\n")
        
        plugins = ['pill_reminder', 'plugin_manager', 'qq_bridge', 'syno_chat_webhook', 'wx_metube']
        for plugin in plugins:
            manifest = read_manifest(plugin)
            if manifest:
                f.write(f"- {manifest.get('name', plugin)} v{manifest.get('version', '1.0.0')}\n")
                f.write(f"  描述: {manifest.get('description', '无描述')}\n")
            else:
                f.write(f"- {plugin} (manifest信息缺失)\n")
        
        f.write("\n安装说明:\n")
        f.write("1. 下载对应的zip文件\n")
        f.write("2. 解压到NotifyHub的plugins目录\n")
        f.write("3. 重启NotifyHub服务\n")
        f.write("4. 在插件管理中启用插件\n")

def create_github_release_script():
    """创建GitHub Release脚本"""
    script_content = '''#!/bin/bash
# GitHub Release 自动发布脚本

# 设置变量
REPO="dysobo/NotifyHub_plugins"
TAG_PREFIX="v"

# 获取当前日期作为版本号
VERSION=$(date +"%Y.%m.%d")

echo "🚀 开始创建GitHub Release..."

# 为每个插件创建Release
plugins=("pill_reminder" "plugin_manager" "qq_bridge" "syno_chat_webhook" "wx_metube")

for plugin in "${plugins[@]}"; do
    echo "📦 处理插件: $plugin"
    
    # 查找对应的zip文件
    zip_file=$(ls packages/${plugin}_v*_*.zip | tail -1)
    
    if [ -f "$zip_file" ]; then
        # 创建标签
        tag="${TAG_PREFIX}${plugin}-${VERSION}"
        
        # 创建Release
        gh release create "$tag" "$zip_file" \\
            --title "${plugin^} v${VERSION}" \\
            --notes "自动发布的 ${plugin} 插件包
        
        更新时间: $(date)
        仓库地址: https://github.com/${REPO}
        
        安装说明:
        1. 下载zip文件
        2. 解压到NotifyHub的plugins目录
        3. 重启NotifyHub服务
        4. 在插件管理中启用插件"
        
        echo "✅ $plugin 发布完成: $tag"
    else
        echo "❌ 找不到 $plugin 的打包文件"
    fi
done

echo "🎉 所有插件发布完成!"
'''
    
    with open('create_releases.sh', 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    # 设置执行权限
    os.chmod('create_releases.sh', 0o755)
    print("📝 已创建GitHub Release脚本: create_releases.sh")

if __name__ == "__main__":
    try:
        # 创建所有插件包
        success = create_all_packages()
        
        if success:
            # 创建GitHub Release脚本
            create_github_release_script()
            
            print("\n[SUCCESS] 所有操作完成!")
            print("[INFO] 下一步:")
            print("1. 检查 packages/ 目录下的zip文件")
            print("2. 运行 ./create_releases.sh 创建GitHub Release")
            print("3. 或者手动上传zip文件到GitHub Release")
        else:
            print("\n[ERROR] 部分插件打包失败，请检查错误信息")
            
    except Exception as e:
        print(f"[ERROR] 打包过程中出现错误: {e}")
