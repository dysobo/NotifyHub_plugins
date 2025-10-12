Synology Chat Webhook Plugin for NotifyHub

Usage

- Place this folder under `/data/plugins/syno_chat_webhook`.
- Restart NotifyHub; routes will be mounted at `/api/plugins/syno_chat_webhook/...`.
- Configure the plugin in the UI:
  - Choose sending target: Router or Channel
  - Select the bound Router or Channel
  - Optional: set `verify_token`, `allowed_channels`, and `title_prefix`
- In Synology Chat, create an Outgoing Webhook pointing to:
  `{site_url}/api/plugins/syno_chat_webhook/webhook`

Incoming Payload

The endpoint accepts Synology Chat Outgoing Webhook payloads with common fields like `token`, `channel_name`, `username`, `text`, `timestamp`, and will forward the content to NotifyHub.


