# QQ群消息转发插件 (OneBot 12) - v0.0.2

## 插件简介

QQ群消息转发插件是一个NotifyHub插件，通过OneBot 12标准对接QQ机器人（如NapCatQQ），接收指定QQ群消息并转发到NotifyHub的渠道或通道，支持企业微信等通知方式。

## 安装部署

1. 将插件文件夹放置到 `/data/plugins/qq_bridge` 目录
2. 重启NotifyHub服务
3. 在插件管理界面配置相关参数

## 接口地址

- **Webhook接收**: `POST {站点地址}/api/plugins/qq_bridge/webhook`
- **健康检查**: `GET {站点地址}/api/plugins/qq_bridge/ping`
- **状态查看**: `GET {站点地址}/api/plugins/qq_bridge/status`
- **测试发送**: `POST {站点地址}/api/plugins/qq_bridge/test`
- **媒体测试**: `POST {站点地址}/api/plugins/qq_bridge/test-media`

## 主要功能

- **OneBot 12标准支持**: 完整支持OneBot 12标准协议
- **丰富消息解析**: 支持图片、表情、@提及、回复、语音、视频、文件、位置、分享链接等
- **媒体文件存储**: 自动下载并存储图片、语音、视频文件到本地
- **媒体链接生成**: 为下载的媒体文件生成可访问的HTTP链接
- **可点击链接**: 第一个媒体链接将作为可点击链接发送，支持在企业微信中直接点击跳转
- **OneBot文件API**: 自动通过OneBot API解析文件ID获取下载链接
- **WebSocket支持**: 实时OneBot连接，支持自动重连
- **HTTP Webhook**: 备用webhook支持，适用于各种OneBot实现
- **群组和用户过滤**: 支持指定QQ群和私聊用户白名单
- **图片转发**: 自动将图片作为推送附件转发

## 配置说明

- **发送目标类型**: 选择Router（按通道）或Channel（按渠道），并绑定对应对象
- **允许的QQ群**: 逗号分隔的群号，留空表示允许所有群
- **允许的联系人**: 逗号分隔的QQ号，留空表示允许所有用户
- **启用OneBot WebSocket监听**: 需要OneBot服务器运行，否则使用HTTP webhook模式
- **OneBot WS地址**: 例如 `ws://127.0.0.1:3001/`
- **OneBot Access Token**: 如果OneBot实现配置了access_token
- **签名密钥**: 如果设置，将校验OneBot的X-Signature
- **标题前缀**: 默认值为 `[QQ群]`

**重要提示**: 如果WebSocket连接失败（HTTP 404），请关闭WebSocket监听，仅使用HTTP webhook模式。

## 调试和测试

### 实时状态监控

```bash
# 查看WebSocket连接状态和配置信息
curl http://你的notifyhub地址/api/plugins/qq_bridge/status
```

返回信息包括：
- WebSocket连接状态（已连接/断开）
- 最后连接/断开时间
- 连接尝试次数
- 接收到的消息统计
- 最后错误信息
- 完整配置信息

### 测试发送

```bash
# 发送普通测试通知
curl -X POST http://你的notifyhub地址/api/plugins/qq_bridge/test

# 发送包含可点击链接的测试通知
curl -X POST http://你的notifyhub地址/api/plugins/qq_bridge/test-media
```

会根据当前配置发送一条测试消息到指定的router或channel。`test-media`端点会发送包含可点击链接的测试消息，用于验证链接点击功能。

### 媒体文件处理

插件会自动下载并存储以下类型的媒体文件：
- **图片**: JPG、PNG、GIF、WebP格式
- **语音**: MP3、WAV、OGG格式  
- **视频**: MP4、AVI格式

媒体文件存储在 `data/plugins/qq_bridge/media/` 目录，并生成可访问的链接：
```
https://你的域名:888/api/plugins/qq_bridge/media/image_1696234567.jpg
```

### 实时监控建议

1. 启用WebSocket后，配置界面会自动显示连接状态
2. 连接状态每5秒自动刷新，无需手动操作
3. 媒体文件会自动下载并在通知中提供链接
4. 如需查看详细错误信息，可访问 `/status` API端点

## OneBot 12配置示例

```yaml
# OneBot 12实现（例如NapCatQQ）
websocket:
  enabled: true
  address: "127.0.0.1:3001"
  access_token: "你的token"

# 或者使用HTTP webhook
post_url: {站点地址}/api/plugins/qq_bridge/webhook
secret: 你的密钥（如果需要）
```

标准文档参考: [OneBot 12 Documentation](https://onebot.dev/)

## 版本历史

### v0.0.2 (2024-12-19)
- ✨ **新增功能**: 支持媒体文件可点击链接
- 🔧 **优化**: 当消息包含媒体文件时，第一个媒体链接将作为可点击链接发送
- 🔧 **优化**: 改进媒体文件显示逻辑，单个媒体文件时简化显示
- 🧪 **新增**: 添加 `/test-media` 测试端点，用于测试可点击链接功能
- 📝 **文档**: 更新帮助文档，说明可点击链接功能

### v0.0.1
- 🎉 **初始版本**: 基本的QQ群消息转发功能
- 🔧 **支持**: OneBot 12标准对接（HTTP webhook + WebSocket）
- 🔧 **支持**: 图片、语音、视频等媒体文件下载和链接生成
- 🔧 **支持**: 消息过滤（群组和用户白名单）
- 🔧 **支持**: 企业微信推送

## 技术支持

如有问题或建议，请通过以下方式联系：
- 查看NotifyHub官方文档
- 提交Issue到相关仓库
- 查看插件日志获取详细错误信息

## 许可证

本插件遵循NotifyHub的插件开发规范和相关许可证。