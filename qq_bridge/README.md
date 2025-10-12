QQ Group Bridge Plugin (OneBot 12)

- Place under `/data/plugins/qq_bridge` and restart NotifyHub
- Webhook: `POST {site_url}/api/plugins/qq_bridge/webhook`
- Health: `GET {site_url}/api/plugins/qq_bridge/ping`
- Status: `GET {site_url}/api/plugins/qq_bridge/status`
- Test: `POST {site_url}/api/plugins/qq_bridge/test`

Features

- **OneBot 12 Compliant**: Full support for OneBot 12 standard
- **Rich Message Parsing**: Images, emojis, @mentions, replies, voice, video, files, location, shares
- **Media Storage**: Automatically downloads and stores images, voice, video files
- **Media Links**: Generates accessible links for downloaded media files
- **OneBot File API**: Automatically resolves file IDs to download URLs using OneBot API
- **WebSocket Support**: Real-time OneBot connection with auto-reconnect
- **HTTP Webhook**: Fallback webhook support for OneBot implementations
- **Group & User Filtering**: Whitelist specific QQ groups and private chat users
- **Image Forwarding**: Automatically forwards images as push attachments

Config

- 发送目标类型: Router 或 Channel，并绑定对应对象
- 允许的QQ群: 逗号分隔的群号，留空允许所有群
- 允许的联系人: 逗号分隔的QQ号，留空允许所有用户
- 启用 OneBot WebSocket 监听: 需要 OneBot 服务器运行，否则使用 HTTP webhook
- OneBot WS 地址: 如 `ws://127.0.0.1:3001/`
- OneBot Access Token: 若 OneBot 实现配置了 access_token
- 签名密钥: 若设置，将校验 OneBot 的 `X-Signature`
- 标题前缀: 默认 `[QQ群]`

**注意**: 如果 WebSocket 连接失败（HTTP 404），请关闭 WebSocket 监听，仅使用 HTTP webhook 模式。

## 调试和测试

### 实时状态监控
```bash
# 查看 WebSocket 连接状态和配置
curl http://your-notifyhub/api/plugins/qq_bridge/status
```

返回信息包括：
- WebSocket 连接状态（已连接/断开）
- 最后连接/断开时间
- 连接尝试次数
- 接收到的消息统计
- 最后错误信息
- 完整配置信息

### 测试发送
```bash
# 发送测试通知
curl -X POST http://your-notifyhub/api/plugins/qq_bridge/test
```

会根据当前配置发送一条测试消息到指定的 router 或 channel。

### 媒体文件处理
插件会自动下载并存储以下类型的媒体文件：
- **图片**: JPG, PNG, GIF, WebP 格式
- **语音**: MP3, WAV, OGG 格式  
- **视频**: MP4, AVI 格式

媒体文件存储在 `data/plugins/qq_bridge/media/` 目录，并生成可访问的链接：
```
https://nh.dysobo.cn:888/api/plugins/qq_bridge/media/image_1696234567.jpg
```

### 实时监控建议
1. 启用 WebSocket 后，配置界面会自动显示连接状态
2. 连接状态每5秒自动刷新，无需手动操作
3. 媒体文件会自动下载并在通知中提供链接
4. 如需查看详细错误信息，可访问 `/status` API 端点

OneBot 12 Setup

```yaml
# OneBot 12 implementation (e.g., NapCatQQ)
websocket:
  enabled: true
  address: "127.0.0.1:3001"
  access_token: "your-token"

# Or HTTP webhook
post_url: {site_url}/api/plugins/qq_bridge/webhook
secret: your-secret-if-needed
```

Standard Reference: [OneBot 12 Documentation](https://onebot.dev/)


