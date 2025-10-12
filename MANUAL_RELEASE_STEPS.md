# 手动发布插件包步骤指南

## 📦 当前状态

✅ **已完成:**
- 5个插件已成功打包为zip文件
- Git标签已创建并推送到GitHub
- GitHub Actions工作流已配置

## 🏷️ 已创建的标签

以下标签已推送到GitHub，可以用于创建Release：

1. `plugin-用药提醒-2025.10.12`
2. `plugin-插件管理器-2025.10.12`
3. `plugin-QQ群消息转发-2025.10.12`
4. `plugin-群晖Chat群组Webhook转发-2025.10.12`
5. `plugin-企业微信MeTube下载器-2025.10.12`

## 📁 插件包文件

对应的zip文件位于 `packages/` 目录：

1. `用药提醒_v0.0.1_20251012_145923.zip`
2. `插件管理器_v1.0.0_20251012_145923.zip`
3. `QQ群消息转发_v0.0.1_20251012_145923.zip`
4. `群晖Chat群组Webhook转发_v0.0.1_20251012_145923.zip`
5. `企业微信MeTube下载器_v0.0.1_20251012_145923.zip`

## 🚀 手动创建Release步骤

### 方法1: 通过GitHub网页界面

1. **访问Release页面**
   - 打开: https://github.com/dysobo/NotifyHub_plugins/releases

2. **创建新Release**
   - 点击 "Create a new release" 按钮

3. **选择标签**
   - 在 "Choose a tag" 下拉菜单中选择对应的标签
   - 例如: `plugin-用药提醒-2025.10.12`

4. **填写Release信息**
   - **Release title**: `用药提醒 v0.0.1`
   - **Description**: 使用以下模板

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

5. **上传文件**
   - 在 "Attach binaries" 部分点击 "Choose your files"
   - 选择对应的zip文件

6. **发布**
   - 点击 "Publish release" 按钮

### 方法2: 使用GitHub Actions (自动)

1. **访问Actions页面**
   - 打开: https://github.com/dysobo/NotifyHub_plugins/actions

2. **选择工作流**
   - 点击 "自动发布插件包" 工作流

3. **手动触发**
   - 点击 "Run workflow" 按钮
   - 选择插件名称或 "all"
   - 点击 "Run workflow"

## 📋 详细对应关系

| 标签名 | 插件包文件 | 插件名称 | 版本 |
|--------|------------|----------|------|
| plugin-用药提醒-2025.10.12 | 用药提醒_v0.0.1_20251012_145923.zip | 用药提醒 | 0.0.1 |
| plugin-插件管理器-2025.10.12 | 插件管理器_v1.0.0_20251012_145923.zip | 插件管理器 | 1.0.0 |
| plugin-QQ群消息转发-2025.10.12 | QQ群消息转发_v0.0.1_20251012_145923.zip | QQ群消息转发 | 0.0.1 |
| plugin-群晖Chat群组Webhook转发-2025.10.12 | 群晖Chat群组Webhook转发_v0.0.1_20251012_145923.zip | 群晖Chat群组Webhook转发 | 0.0.1 |
| plugin-企业微信MeTube下载器-2025.10.12 | 企业微信MeTube下载器_v0.0.1_20251012_145923.zip | 企业微信MeTube下载器 | 0.0.1 |

## ✅ 验证发布结果

发布完成后，你可以：

1. **查看Release页面**
   - https://github.com/dysobo/NotifyHub_plugins/releases
   - 确认所有插件都已发布

2. **测试下载**
   - 点击每个Release的zip文件下载链接
   - 确认文件可以正常下载

3. **检查文件完整性**
   - 解压zip文件
   - 确认包含所有必要的插件文件

## 🔧 故障排除

如果遇到问题：

1. **标签不存在**
   - 检查标签是否正确推送: `git tag -l 'plugin-*'`

2. **文件上传失败**
   - 确认zip文件存在且未损坏
   - 检查文件大小是否超过GitHub限制 (25MB)

3. **权限问题**
   - 确认有仓库的写权限
   - 检查GitHub Token是否有效

## 📞 支持

如有问题请：
1. 检查本指南的故障排除部分
2. 提交Issue: https://github.com/dysobo/NotifyHub_plugins/issues
3. 查看Actions日志获取详细错误信息

---

*最后更新: 2025-10-12*
