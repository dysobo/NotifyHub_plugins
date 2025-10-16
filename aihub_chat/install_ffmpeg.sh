#!/bin/bash

# AIHub Chat 插件 - ffmpeg 安装脚本
# 用于 Docker 容器或 Linux 系统

echo "================================================"
echo "  AIHub Chat 插件 - ffmpeg 安装工具"
echo "================================================"
echo ""

# 检测系统类型
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "❌ 无法检测系统类型"
    exit 1
fi

echo "检测到系统: $OS"
echo ""

# 检查 ffmpeg 是否已安装
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg 已安装"
    ffmpeg -version | head -n 1
    echo ""
    echo "如需重新安装，请先卸载现有版本"
    exit 0
fi

echo "⏳ 开始安装 ffmpeg..."
echo ""

# 根据系统类型安装
case "$OS" in
    ubuntu|debian)
        echo "使用 apt 安装..."
        apt-get update
        apt-get install -y ffmpeg
        ;;
    centos|rhel|fedora)
        echo "使用 yum 安装..."
        yum install -y epel-release
        yum install -y ffmpeg
        ;;
    alpine)
        echo "使用 apk 安装..."
        apk add --no-cache ffmpeg
        ;;
    *)
        echo "❌ 不支持的系统: $OS"
        echo "请手动安装 ffmpeg"
        exit 1
        ;;
esac

# 验证安装
echo ""
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg 安装成功！"
    ffmpeg -version | head -n 1
    echo ""
    echo "================================================"
    echo "  安装完成！请重启 NotifyHub 服务"
    echo "================================================"
else
    echo "❌ ffmpeg 安装失败"
    echo "请手动安装或查看日志"
    exit 1
fi

