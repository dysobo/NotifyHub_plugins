#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动创建Git标签的脚本
为每个插件自动创建版本标签并推送
"""

import os
import json
import subprocess
import glob
from datetime import datetime

def run_command(cmd):
    """执行命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def get_plugin_info(plugin_name):
    """获取插件信息"""
    manifest_path = f"{plugin_name}/manifest.json"
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def create_tag_for_plugin(plugin_name):
    """为插件创建Git标签"""
    print(f"正在为 {plugin_name} 创建标签...")
    
    # 获取插件信息
    manifest = get_plugin_info(plugin_name)
    version = manifest.get('version', '1.0.0') if manifest else '1.0.0'
    timestamp = datetime.now().strftime('%Y.%m.%d')
    tag_name = f"plugin-{plugin_name}-{timestamp}"
    
    # 创建标签
    cmd = f'git tag -a "{tag_name}" -m "Release {plugin_name} v{version}"'
    success, stdout, stderr = run_command(cmd)
    
    if success:
        print(f"[SUCCESS] 标签创建成功: {tag_name}")
        return tag_name
    else:
        print(f"[ERROR] 标签创建失败: {stderr}")
        return None

def push_tags():
    """推送所有标签到远程仓库"""
    print("正在推送标签到远程仓库...")
    success, stdout, stderr = run_command("git push origin --tags")
    
    if success:
        print("[SUCCESS] 标签推送成功")
        return True
    else:
        print(f"[ERROR] 标签推送失败: {stderr}")
        return False

def create_release_info():
    """创建发布信息文件"""
    info_file = "RELEASE_TAGS.txt"
    
    with open(info_file, 'w', encoding='utf-8') as f:
        f.write("NotifyHub 插件发布标签信息\n")
        f.write("=" * 40 + "\n")
        f.write(f"创建时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"仓库地址: https://github.com/dysobo/NotifyHub_plugins\n")
        f.write("\n插件标签列表:\n")
        
        # 获取所有标签
        success, stdout, stderr = run_command("git tag -l 'plugin-*'")
        if success:
            tags = stdout.strip().split('\n')
            for tag in tags:
                if tag:
                    f.write(f"- {tag}\n")
        
        f.write("\n手动创建Release步骤:\n")
        f.write("1. 访问: https://github.com/dysobo/NotifyHub_plugins/releases\n")
        f.write("2. 点击 'Create a new release'\n")
        f.write("3. 选择对应的标签\n")
        f.write("4. 填写Release标题和描述\n")
        f.write("5. 上传对应的zip文件\n")
        f.write("6. 点击 'Publish release'\n")
        
        f.write("\n插件包文件对应关系:\n")
        zip_files = glob.glob('packages/*.zip')
        for zip_file in zip_files:
            filename = os.path.basename(zip_file)
            plugin_name = filename.split('_')[0]
            tag_name = f"plugin-{plugin_name}-{datetime.now().strftime('%Y.%m.%d')}"
            f.write(f"- {tag_name} -> {filename}\n")

def main():
    """主函数"""
    print("NotifyHub 插件自动标签创建工具")
    print("=" * 50)
    
    # 检查packages目录
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
    
    print("\n开始为所有插件创建Git标签...")
    
    # 为所有插件创建标签
    success_count = 0
    created_tags = []
    
    for zip_file in zip_files:
        # 从文件名提取插件名
        filename = os.path.basename(zip_file)
        plugin_name = filename.split('_')[0]
        
        tag_name = create_tag_for_plugin(plugin_name)
        if tag_name:
            created_tags.append(tag_name)
            success_count += 1
        print("-" * 30)
    
    # 推送标签
    if created_tags:
        if push_tags():
            print(f"\n[SUCCESS] 成功创建并推送 {success_count} 个标签")
            
            # 创建发布信息文件
            create_release_info()
            
            print("\n下一步操作:")
            print("1. 访问: https://github.com/dysobo/NotifyHub_plugins/releases")
            print("2. 为每个标签手动创建Release")
            print("3. 上传对应的zip文件")
            print("4. 查看 RELEASE_TAGS.txt 获取详细信息")
        else:
            print("\n[ERROR] 标签推送失败")
    else:
        print("\n[ERROR] 没有成功创建任何标签")

if __name__ == "__main__":
    main()
