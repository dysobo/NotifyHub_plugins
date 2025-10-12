#!/bin/bash
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
        gh release create "$tag" "$zip_file" \
            --title "${plugin^} v${VERSION}" \
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
