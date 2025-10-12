# 插件管理器 - 应用商店

一个功能强大的插件管理应用商店，为 NotifyHub 提供插件仓库管理、插件下载安装、版本管理和备份恢复等功能。

## 🔧 问题诊断

如果遇到页面白屏或API错误，请按以下步骤诊断：

### 1. 访问调试页面
```
https://您的域名:端口/common/view?hidePadding=true#/api/plugins/plugin_manager/frontend/debug.html
```

### 2. 访问API测试页面
```
https://您的域名:端口/common/view?hidePadding=true#/api/plugins/plugin_manager/frontend/api-test.html
```

### 3. 常见问题解决
- **API 500错误**：已修复`convert_github_url_to_raw`函数缺失问题
- **页面白屏**：检查浏览器控制台错误信息
- **CDN加载失败**：使用备用版本`fallback.html`
- **仓库连接失败**：检查网络连接和代理设置

## 功能特性

### 🔧 网络代理支持
- 支持HTTP/HTTPS代理设置
- 可配置代理地址（如：http://192.168.0.250:7890）
- 支持代理开关控制

### 📦 仓库管理
- 支持添加自定义插件仓库
- 默认包含官方仓库和社区仓库
- 仓库启用/禁用控制
- 仓库信息编辑和删除

### 🛍️ 应用商店
- 插件浏览和搜索
- 按分类筛选插件
- 插件详细信息展示
- 一键下载安装插件
- 插件版本检查

### 📱 插件管理
- 查看已安装插件列表
- 插件卸载功能
- 插件版本管理
- 自动更新检查

### 💾 备份管理
- 插件一键备份
- 备份文件管理
- 插件恢复功能
- 备份保留策略

## 安装说明

1. 将 `plugin_manager` 文件夹复制到 `/data/plugins/` 目录下
2. 重启 NotifyHub 服务
3. 在插件配置页面启用插件管理器
4. 访问应用商店的几种方式：
   - **方式1**：在左侧菜单中找到"插件" → "插件页面" → 点击"应用商店"卡片
   - **方式2**：在左侧菜单中找到"插件" → 在插件列表中找到"插件管理器" → 点击进入
   - **方式3**：直接访问URL：`/common/view?hidePadding=true#/api/plugins/plugin_manager/frontend/index.html`

### 找不到入口的解决方案：

#### 🔍 检查步骤：
1. **确认插件状态**：在插件配置页面确认"插件管理器"已启用
2. **刷新页面**：按F5或Ctrl+F5刷新浏览器页面
3. **清除缓存**：清除浏览器缓存和Cookie
4. **检查版本**：确认NotifyHub版本支持插件前端页面功能
5. **查看控制台**：按F12打开开发者工具，查看Console是否有错误
6. **重启服务**：重启NotifyHub服务

#### 🚨 常见问题：

**问题1：菜单中没有"插件页面"**
- **原因**：NotifyHub版本可能不支持前端页面功能
- **解决**：升级NotifyHub到支持插件的版本

**问题2：点击后显示空白页**
- **原因**：前端文件加载失败或JavaScript错误
- **解决**：检查浏览器控制台错误信息，确认前端文件路径正确

**问题3：API测试失败**
- **原因**：插件后端可能未正确加载
- **解决**：重启NotifyHub服务，检查插件配置

**问题4：找不到"应用商店"卡片**
- **原因**：插件前端页面配置可能有问题
- **解决**：检查manifest.json中的frontend_page配置

#### 🧪 测试页面：
- **入口测试**：访问 `/api/plugins/plugin_manager/frontend/entry.html`
- **详细测试**：访问 `/api/plugins/plugin_manager/frontend/test.html`

## 配置选项

### 网络代理设置
- **启用网络代理**：是否启用代理下载插件
- **代理地址**：代理服务器地址，格式如 `http://192.168.0.250:7890`

### 默认仓库
- **官方仓库**：NotifyHub官方插件仓库
- **社区仓库**：社区贡献插件仓库

### 其他设置
- **自动检查更新**：是否自动检查插件更新
- **备份保留天数**：备份文件保留天数，0表示永久保留

## API 接口

### 状态接口
- `GET /api/plugins/plugin_manager/status` - 获取插件管理器状态

### 仓库管理
- `GET /api/plugins/plugin_manager/repositories` - 获取仓库列表
- `POST /api/plugins/plugin_manager/repositories` - 添加新仓库
- `PUT /api/plugins/plugin_manager/repositories/{repo_id}` - 更新仓库信息
- `DELETE /api/plugins/plugin_manager/repositories/{repo_id}` - 删除仓库

### 插件管理
- `GET /api/plugins/plugin_manager/plugins/search` - 搜索插件
- `GET /api/plugins/plugin_manager/plugins/{plugin_id}/info` - 获取插件详细信息
- `POST /api/plugins/plugin_manager/plugins/install` - 安装插件
- `DELETE /api/plugins/plugin_manager/plugins/{plugin_id}` - 卸载插件
- `GET /api/plugins/plugin_manager/installed` - 获取已安装插件

### 备份管理
- `GET /api/plugins/plugin_manager/backups` - 获取备份列表
- `POST /api/plugins/plugin_manager/backups` - 创建备份
- `POST /api/plugins/plugin_manager/backups/restore` - 恢复备份
- `DELETE /api/plugins/plugin_manager/backups/{plugin_id}/{backup_file}` - 删除备份

## 仓库格式

### GitHub仓库配置

插件管理器支持自动扫描GitHub仓库，无需手动创建JSON索引文件！

#### 自动扫描功能
系统会自动：
1. **扫描GitHub仓库**：使用GitHub API获取仓库内容
2. **识别插件目录**：查找包含`manifest.json`的目录
3. **生成本地索引**：自动创建JSON索引文件并缓存
4. **智能缓存**：本地缓存1小时，减少API调用

#### 支持的仓库格式
- **仓库根目录**：`https://github.com/用户名/仓库名`
- **子目录**：`https://github.com/用户名/仓库名/tree/main/子目录`

#### 默认仓库配置
- **官方仓库**：`https://github.com/htnanako/NotifyHub_plugins`
- **社区仓库**：`https://github.com/Alano-i/Plugins/tree/main/NH-Plugins`

#### 手动刷新
如果仓库有更新，可以点击仓库列表中的刷新按钮手动更新缓存。

### 仓库JSON格式

插件仓库需要提供 JSON 格式的仓库文件，包含以下结构：

```json
{
  "name": "仓库名称",
  "description": "仓库描述",
  "plugins": [
    {
      "id": "plugin_id",
      "name": "插件名称",
      "description": "插件描述",
      "author": "作者",
      "version": "1.0.0",
      "logo": "https://example.com/logo.png",
      "thumbnailurl": "https://example.com/thumbnail.png",
      "documentation": "https://example.com/docs",
      "download_url": "https://example.com/plugin.zip",
      "file_size": 1024000,
      "category": "工具",
      "install_count": 100,
      "last_updated": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 为GitHub仓库创建索引文件

如果您的GitHub仓库还没有JSON索引文件，请按以下步骤创建：

1. 在仓库根目录创建 `repository.json` 文件
2. 按照上述格式填写仓库信息
3. 为每个插件目录添加对应的插件信息
4. 提交并推送到GitHub

示例：为 [htnanako/NotifyHub_plugins](https://github.com/htnanako/NotifyHub_plugins) 创建索引文件

## 插件包格式

插件包应为 ZIP 格式，包含以下文件：
- `manifest.json` - 插件清单文件
- `__init__.py` - Python包初始化文件
- `*.py` - 插件主要代码文件
- `frontend/` - 前端文件目录（可选）
- `requirements.txt` - 依赖文件（可选）

## 使用说明

### 添加自定义仓库
1. 进入"仓库管理"标签页
2. 点击"添加仓库"按钮
3. 填写仓库信息：
   - 仓库ID：唯一标识符
   - 仓库名称：显示名称
   - 仓库URL：仓库JSON文件地址
   - 仓库描述：可选描述信息
4. 点击"添加"保存

### 安装插件
1. 在"应用商店"标签页浏览插件
2. 使用搜索框查找特定插件
3. 点击插件卡片查看详细信息
4. 点击"安装"按钮开始下载安装

### 管理备份
1. 进入"备份管理"标签页
2. 选择要管理备份的插件
3. 点击"创建备份"创建新备份
4. 使用"恢复"按钮恢复指定备份
5. 使用"删除"按钮清理不需要的备份

## 注意事项

1. 确保网络连接正常，以便下载插件
2. 代理设置需要重启插件才能生效
3. 备份文件会占用存储空间，建议定期清理
4. 卸载插件前建议先创建备份
5. 恢复备份会覆盖当前插件文件

## 故障排除

### 无法下载插件
- 检查网络连接
- 验证代理设置是否正确
- 确认仓库URL可访问

### 插件安装失败
- 检查插件包格式是否正确
- 确认manifest.json文件有效
- 查看系统日志获取详细错误信息

### 备份恢复失败
- 确认备份文件完整
- 检查插件目录权限
- 验证备份文件格式

## 版本历史

### v1.0.0
- 初始版本发布
- 支持基本的插件管理功能
- 提供应用商店界面
- 实现备份恢复功能

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个插件管理器。

## 许可证

本项目采用 MIT 许可证。
