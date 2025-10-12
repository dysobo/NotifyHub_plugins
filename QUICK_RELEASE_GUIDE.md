# 快速发布指南

## 🚀 立即发布所有插件

由于GitHub Actions工作流遇到了一些技术问题，我为你提供了多种发布方式：

### 方法1: 手动在GitHub网页上创建Release (最简单)

1. **访问Release页面**
   - 打开: https://github.com/dysobo/NotifyHub_plugins/releases

2. **创建Release**
   - 点击 "Create a new release"
   - 选择标签: `plugin-用药提醒-2025.10.12`
   - 标题: `用药提醒 v0.0.1`
   - 描述: 复制下面的模板

3. **上传文件**
   - 上传对应的zip文件: `用药提醒_v0.0.1_20251012_145923.zip`

4. **重复以上步骤**
   - 为其他4个插件创建Release

### 方法2: 使用Python脚本 (需要GitHub Token)

```bash
# 运行发布脚本
python create_releases_now.py
```

**需要GitHub Personal Access Token:**
1. 访问: https://github.com/settings/tokens
2. 创建新的token，权限选择 `repo`
3. 设置环境变量: `export GITHUB_TOKEN=your_token`

### 方法3: 使用GitHub Actions (修复后)

1. 访问: https://github.com/dysobo/NotifyHub_plugins/actions
2. 选择 "创建插件Release" 工作流
3. 点击 "Run workflow"

## 📋 发布信息模板

### 用药提醒 Release
- **标签**: `plugin-用药提醒-2025.10.12`
- **标题**: `用药提醒 v0.0.1`
- **文件**: `用药提醒_v0.0.1_20251012_145923.zip`

**描述模板:**
```markdown
自动发布的 用药提醒 插件包

**插件信息:**
- 名称: 用药提醒
- 版本: 0.0.1
- 描述: 用药提醒管理
- 作者: 未知

**更新时间:** 2025-10-12 15:06:49
**仓库地址:** https://github.com/dysobo/NotifyHub_plugins

**安装说明:**
1. 下载zip文件
2. 解压到NotifyHub的plugins目录
3. 重启NotifyHub服务
4. 在插件管理中启用插件

**注意事项:**
- 请确保NotifyHub版本兼容
- 安装前请备份现有配置
- 如有问题请提交Issue反馈
```

### 其他插件信息

| 插件名称 | 标签 | 标题 | 文件 |
|----------|------|------|------|
| 插件管理器 | `plugin-插件管理器-2025.10.12` | `插件管理器 v1.0.0` | `插件管理器_v1.0.0_20251012_145923.zip` |
| QQ群消息转发 | `plugin-QQ群消息转发-2025.10.12` | `QQ群消息转发 v0.0.1` | `QQ群消息转发_v0.0.1_20251012_145923.zip` |
| 群晖Chat推送 | `plugin-群晖Chat群组Webhook转发-2025.10.12` | `群晖Chat群组Webhook转发 v0.0.1` | `群晖Chat群组Webhook转发_v0.0.1_20251012_145923.zip` |
| 企业微信MeTube | `plugin-企业微信MeTube下载器-2025.10.12` | `企业微信MeTube下载器 v0.0.1` | `企业微信MeTube下载器_v0.0.1_20251012_145923.zip` |

## ✅ 验证发布

发布完成后：
1. 访问: https://github.com/dysobo/NotifyHub_plugins/releases
2. 确认所有5个插件都已发布
3. 测试下载链接

## 🔧 故障排除

如果遇到问题：
1. **权限问题**: 确认有仓库的写权限
2. **文件上传失败**: 检查zip文件大小 (< 25MB)
3. **标签不存在**: 检查标签是否正确推送

---

**推荐**: 使用方法1 (手动创建) 最可靠，只需要5分钟就能完成所有插件的发布！
