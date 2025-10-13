# 群晖Chat Webhook插件

## 插件简介

群晖Chat Webhook插件是一个NotifyHub插件，用于接收群晖Chat（Synology Chat）的Webhook消息，并将其转发到NotifyHub的渠道或通道，支持企业微信等通知方式。

## 安装部署

1. 将插件文件夹放置到 `/data/plugins/syno_chat_webhook` 目录
2. 重启NotifyHub服务，路由将挂载到 `/api/plugins/syno_chat_webhook/...`
3. 在插件管理界面配置相关参数

## 配置说明

在NotifyHub插件管理界面中配置以下参数：

- **发送目标类型**: 选择Router（按通道）或Channel（按渠道）
- **绑定对象**: 选择对应的Router或Channel
- **验证令牌**（可选）: 设置`verify_token`用于验证消息来源
- **允许的频道**（可选）: 设置`allowed_channels`限制接收的频道
- **标题前缀**（可选）: 设置`title_prefix`自定义消息标题前缀

## 群晖Chat配置

在群晖Chat中创建出站Webhook，指向以下地址：
```
{你的站点地址}/api/plugins/syno_chat_webhook/webhook
```

## 消息处理

该插件接收群晖Chat的出站Webhook消息，包含以下常见字段：
- `token`: 验证令牌
- `channel_name`: 频道名称
- `username`: 用户名
- `text`: 消息内容
- `timestamp`: 时间戳

插件会将接收到的消息内容转发到NotifyHub，然后发送到配置的目标渠道或通道。

## 使用场景

- 群晖NAS用户通过Chat发送消息到企业微信群
- 将群晖Chat的频道消息转发到其他通知平台
- 集成群晖Chat到现有的通知工作流中

## 技术支持

如有问题或建议，请通过以下方式联系：
- 查看NotifyHub官方文档
- 提交Issue到相关仓库
- 查看插件日志获取详细错误信息

## 许可证

本插件遵循NotifyHub的插件开发规范和相关许可证。