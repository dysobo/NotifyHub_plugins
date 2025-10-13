# 企业微信MeTube下载器插件

## 插件简介

企业微信MeTube下载器是一个NotifyHub插件，可以通过企业微信接收YouTube等视频链接，自动提交到MeTube进行下载，并在下载完成后推送下载链接到企业微信。

## 主要功能

- 📱 **企业微信集成**：通过企业微信接收视频链接
- 🎬 **自动下载**：自动提交到MeTube下载队列
- 🔔 **智能通知**：下载完成后推送文件下载链接
- 🌐 **多平台支持**：支持YouTube、Bilibili等主流视频网站
- ⚙️ **灵活配置**：支持自定义下载质量和格式

## 安装部署

### 1. 部署MeTube

#### 群晖NAS部署

使用提供的Docker Compose文件在群晖NAS上部署MeTube：

**1. 创建docker-compose.yml文件**

在群晖的`/volume1/docker/metube/`目录下创建`docker-compose.yml`文件：

```yaml
version: '3.8'

services:
  # MeTube服务 - 群晖NAS部署版本
  metube:
    image: ghcr.io/alexta69/metube:latest
    container_name: metube
    restart: unless-stopped
    ports:
      - "8081:8081"
    volumes:
      # 群晖NAS映射路径
      - /volume6/Download/metube:/downloads
    environment:
      # MeTube基础配置
      - DOWNLOAD_DIR=/downloads
      - AUDIO_DOWNLOAD_DIR=/downloads
      - DEFAULT_THEME=auto
      - CUSTOM_DIRS=true
      - CREATE_CUSTOM_DIRS=true
      
      # 下载模式配置 - 群晖优化
      - DOWNLOAD_MODE=limited
      - MAX_CONCURRENT_DOWNLOADS=2
      
      # 日志配置
      - LOGLEVEL=INFO
      
      # 输出模板配置
      - OUTPUT_TEMPLATE=%(title)s.%(ext)s
      - OUTPUT_TEMPLATE_PLAYLIST=%(playlist_title)s/%(title)s.%(ext)s
      
      # 群晖用户权限配置
      - UID=1026
      - GID=100
      - UMASK=022
      
      # 其他配置
      - DOWNLOAD_DIRS_INDEXABLE=true
      - DELETE_FILE_ON_TRASHCAN=false
      
      # 群晖网络配置
      - TZ=Asia/Shanghai
    networks:
      - metube-network
    # 健康检查
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:8081/version"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    # 日志配置
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

# 网络配置
networks:
  metube-network:
    driver: bridge
    ipam:
      config:
        - subnet: 172.20.0.0/16

# 数据卷
volumes:
  metube-downloads:
    driver: local
```

**2. 部署MeTube服务**

```bash
# SSH连接到群晖
ssh admin@your-nas-ip

# 切换到docker-compose文件目录
cd /volume1/docker/metube

# 启动MeTube服务
sudo docker-compose up -d

# 检查服务状态
sudo docker-compose ps

# 查看日志
sudo docker-compose logs -f metube
```

**群晖部署特点**：
- 下载目录映射：`/volume6/Download/metube:/downloads`
- 优化的用户权限：UID=1026, GID=100
- 并发下载：限制为2个并发任务
- 时区设置：Asia/Shanghai
- 健康检查：自动监控服务状态
- 日志管理：限制日志文件大小，避免占用过多存储空间

MeTube将在 `http://your-nas-ip:8081` 启动。

#### 其他环境部署

```bash
# 启动MeTube服务
docker-compose up -d

# 检查服务状态
docker-compose ps

# 查看日志
docker-compose logs -f metube
```

### 2. 安装插件

1. **复制插件文件**到NotifyHub的插件目录：
   ```bash
   cp -r wx_metube /data/plugins/
   ```

2. **重启NotifyHub服务**以加载插件

3. **配置插件**：
   - 在NotifyHub管理界面找到"企业微信MeTube下载器"插件
   - 配置企业微信应用信息
   - 设置MeTube服务地址

## 配置说明

### 企业微信配置

| 配置项 | 说明 | 示例 |
|--------|------|------|
| 企业微信CorpID | 企业微信的企业ID | ww1234567890abcdef |
| 企业微信Secret | 企业微信应用的Secret | abcdef1234567890 |
| 企业微信AgentID | 企业微信应用的AgentID | 1000001 |
| 企业微信Token | 接收消息的Token | your_token_here |
| 企业微信EncodingAESKey | 消息加密的AESKey | your_aes_key_here |

### MeTube配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| MeTube服务地址 | MeTube的完整访问地址 | http://192.168.0.88:8081 |
| 默认下载质量 | 提交下载时的默认质量 | best |
| 默认下载格式 | 提交下载时的默认格式 | any |
| 自动开始下载 | 是否自动开始下载 | 开启 |

### 回调地址配置

在企业微信应用中配置回调地址：

```
https://your-notifyhub-domain.com/api/plugins/wx_metube/chat
```

## 使用方法

### 1. 发送视频链接

在企业微信中直接发送YouTube等视频链接：

```
https://www.youtube.com/watch?v=xxx
```

或者发送带描述的链接：

```
下载这个视频：https://youtu.be/xxx
```

### 2. 自动处理流程

1. **接收链接**：插件接收企业微信消息中的视频链接
2. **提交下载**：自动提交到MeTube下载队列
3. **确认通知**：发送"已提交下载"的确认消息
4. **监控进度**：后台监控下载状态
5. **完成通知**：下载完成后推送文件下载链接

### 3. 下载完成通知

下载完成后，会收到类似以下格式的通知：

```
🎉 视频下载完成！

📹 标题：飞牛VS黑群VS极空间，「最」详细的NAS系统对比
📁 文件：飞牛VS黑群VS极空间，「最」详细的NAS系统对比.mp4
🔗 下载链接：http://192.168.0.88:8081/download/%E9%A3%9E%E7%89%9BVS%E9%BB%91%E7%BE%A4VS%E6%9E%81%E7%A9%BA%E9%97%B4%EF%BC%8C%E3%80%8C%E6%9C%80%E3%80%8D%E8%AF%A6%E7%BB%86%E7%9A%84NAS%E7%B3%BB%E7%BB%9F%E5%AF%B9%E6%AF%94.mp4

点击链接即可下载文件
```

## API接口

### 获取插件状态

```http
GET /api/plugins/wx_metube/status
```

返回插件运行状态、MeTube连接状态和配置信息。

### 测试MeTube连接

```http
POST /api/plugins/wx_metube/test-metube
```

测试与MeTube服务的连接状态。

### 手动检查下载

```http
POST /api/plugins/wx_metube/manual-check
```

手动触发一次下载状态检查。

### 重载配置

```http
POST /api/plugins/wx_metube/reload-config
```

重新加载插件配置。

## 前端监控面板

插件提供了一个Web监控面板，可以通过以下方式访问：

```
http://your-notifyhub-domain/common/view?hidePadding=true#/api/plugins/wx_metube/frontend/index.html
```

### 面板功能

- 📊 **实时状态**：显示MeTube连接状态和插件配置
- 🔄 **手动操作**：提供测试连接、手动检查等操作按钮
- 🧪 **测试功能**：可以测试下载提交功能
- ⚙️ **配置状态**：显示当前配置的完整性

## 支持的网站

插件支持所有yt-dlp支持的视频网站，包括但不限于：

- **YouTube** (youtube.com, youtu.be)
- **Bilibili** (bilibili.com)
- **Vimeo** (vimeo.com)
- **Twitter** (twitter.com)
- **Instagram** (instagram.com)
- **TikTok** (tiktok.com)

可以通过配置 `supported_domains` 参数来限制支持的网站。

## 故障排除

### 常见问题

1. **企业微信消息无法接收**
   - 检查企业微信应用配置是否正确
   - 确认回调地址是否可以访问
   - 验证Token和EncodingAESKey是否正确

2. **MeTube连接失败**
   - 确认MeTube服务是否正常运行
   - 检查网络连接和端口配置
   - 验证MeTube服务地址是否正确

3. **下载提交失败**
   - 检查URL是否为有效的视频链接
   - 确认MeTube服务是否正常响应
   - 查看插件日志获取详细错误信息

4. **下载完成通知未发送**
   - 确认企业微信配置是否正确
   - 检查下载监控是否正常运行
   - 验证文件是否确实下载完成

5. **群晖部署相关问题**
   - **容器无法启动**：检查docker-compose.yml语法和端口占用
   - **文件权限问题**：确认UID/GID配置正确（UID=1026, GID=100）
   - **存储空间不足**：检查`/volume6/Download/metube`目录空间
   - **网络访问问题**：确认群晖防火墙允许8081端口访问

### 日志查看

插件运行日志可以通过NotifyHub的日志系统查看，日志标识为：`wx_metube`

### 调试模式

可以通过API接口手动触发各种操作来调试插件功能：

```bash
# 测试MeTube连接
curl -X POST http://localhost:8080/api/plugins/wx_metube/test-metube

# 获取插件状态
curl http://localhost:8080/api/plugins/wx_metube/status

# 手动检查下载
curl -X POST http://localhost:8080/api/plugins/wx_metube/manual-check

# 调试企业微信回调配置
curl http://localhost:8080/api/plugins/wx_metube/debug/callback
```

#### 群晖环境调试

```bash
# 检查MeTube容器状态
sudo docker ps | grep metube

# 查看MeTube容器日志
sudo docker logs metube

# 检查下载目录权限
ls -la /volume6/Download/metube

# 测试MeTube服务访问
curl http://your-nas-ip:8081/version

# 检查端口占用
sudo netstat -tlnp | grep 8081
```

## 性能建议

1. **下载队列**：建议设置合理的并发下载数量
2. **智能监控**：插件采用智能检查频率
   - 前3分钟：每10秒检查一次
   - 3-10分钟：每1分钟检查一次
   - 10-50分钟：每5分钟检查一次
   - 50分钟-2小时：每10分钟检查一次
   - 2-72小时：每24小时检查一次
   - 72小时后：停止检查
3. **缓存策略**：下载记录缓存1小时，避免重复通知
4. **网络优化**：确保NotifyHub和MeTube之间的网络连接稳定

## 版本历史

### v0.0.2 (2024-12-19)
- 🔧 **性能优化**：调整定时任务频率从每分钟改为每5分钟，减少系统资源占用
- 🚫 **去重机制**：新增已处理下载缓存，避免重复检查和推送已完成下载
- 📝 **日志优化**：减少不必要的重复日志输出，改用debug级别记录常规检查
- 💾 **缓存优化**：扩展缓存容量和TTL时间，提高系统稳定性
- 🔍 **监控增强**：新增已处理下载记录查看和缓存清理API
- 🐛 **修复**：解决系统日志中出现大量重复日志导致卡顿的问题

### v0.0.1
- 🎉 **初始版本**：基本的QQ群消息转发功能
- 🔧 **支持**：OneBot 12标准对接（HTTP webhook + WebSocket）
- 🔧 **支持**：图片、语音、视频等媒体文件下载和链接生成
- 🔧 **支持**：消息过滤（群组和用户白名单）
- 🔧 **支持**：企业微信推送

## 技术支持

如有问题或建议，请通过以下方式联系：

- 查看NotifyHub官方文档
- 提交Issue到相关仓库
- 查看插件日志获取详细错误信息

## 许可证

本插件遵循NotifyHub的插件开发规范和相关许可证。
