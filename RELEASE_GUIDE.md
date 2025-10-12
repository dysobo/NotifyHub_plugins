# NotifyHub 插件发布指南

本指南说明如何自动打包和发布NotifyHub插件到GitHub Releases。

## 📦 插件列表

当前仓库包含以下5个插件：

1. **pill_reminder** - 用药提醒
2. **plugin_manager** - 插件管理器  
3. **qq_bridge** - QQ群信息桥接
4. **syno_chat_webhook** - 群晖Chat推送
5. **wx_metube** - 企业微信MeTube集成

## 🚀 自动发布方法

### 方法1: 使用Python脚本 (推荐)

#### 步骤1: 打包所有插件
```bash
python package_plugins.py
```

这会：
- 自动读取每个插件的manifest.json
- 为每个插件创建独立的zip包
- 将包保存在`packages/`目录下

#### 步骤2: 发布到GitHub Releases
```bash
python release_all_plugins.py
```

**前提条件:**
- 安装GitHub CLI: https://cli.github.com/
- 配置认证: `gh auth login`

### 方法2: 使用GitHub Actions (自动)

#### 手动触发发布
1. 访问: https://github.com/dysobo/NotifyHub_plugins/actions
2. 选择"自动发布插件包"工作流
3. 点击"Run workflow"
4. 选择要发布的插件或选择"all"发布所有插件

#### 通过标签触发发布
```bash
# 发布单个插件
git tag plugin-pill_reminder-2025.01.12
git push origin plugin-pill_reminder-2025.01.12

# 发布所有插件 (需要先打包)
git tag plugin-all-2025.01.12
git push origin plugin-all-2025.01.12
```

## 📋 发布流程详解

### 1. 插件打包流程
```
插件目录 → 读取manifest.json → 创建zip包 → 保存到packages/
```

每个插件包包含：
- 所有插件文件 (排除__pycache__, .git等)
- manifest.json配置文件
- README.md说明文档
- requirements.txt依赖文件 (如果有)

### 2. GitHub Release创建
```
zip文件 → 创建标签 → 生成Release → 上传文件
```

每个Release包含：
- 版本标签 (格式: plugin-{name}-{date})
- 详细的发布说明
- 安装指南
- 插件信息

## 📁 文件结构

```
NotifyHub_plugins/
├── .github/workflows/
│   └── release-plugins.yml    # GitHub Actions工作流
├── packages/                  # 打包输出目录
│   ├── *.zip                 # 插件包文件
│   └── PACKAGE_INFO.txt      # 打包信息
├── package_plugins.py        # 打包脚本
├── release_all_plugins.py    # 发布脚本
└── RELEASE_GUIDE.md          # 本指南
```

## 🔧 配置说明

### 插件manifest.json格式
```json
{
  "name": "插件名称",
  "version": "1.0.0",
  "description": "插件描述",
  "author": "作者",
  "dependencies": ["依赖列表"]
}
```

### GitHub Actions配置
- 支持手动触发和标签触发
- 自动打包和发布
- 支持单个插件或全部插件发布

## 📥 用户下载安装

### 下载插件
1. 访问: https://github.com/dysobo/NotifyHub_plugins/releases
2. 选择需要的插件版本
3. 下载对应的zip文件

### 安装插件
1. 解压zip文件到NotifyHub的plugins目录
2. 重启NotifyHub服务
3. 在插件管理中启用插件

## 🛠️ 故障排除

### 常见问题

1. **打包失败**
   - 检查插件目录是否存在
   - 确认manifest.json格式正确

2. **发布失败**
   - 检查GitHub CLI是否安装: `gh --version`
   - 确认已登录: `gh auth status`
   - 检查网络连接

3. **GitHub Actions失败**
   - 检查仓库权限设置
   - 确认GITHUB_TOKEN有足够权限
   - 查看Actions日志获取详细错误信息

### 手动操作
如果自动脚本失败，可以手动操作：

1. **手动打包**
   ```bash
   # 进入插件目录
   cd plugin_name
   
   # 创建zip包
   zip -r ../plugin_name.zip . -x "*.pyc" "__pycache__/*"
   ```

2. **手动发布**
   ```bash
   # 创建Release
   gh release create "plugin-name-2025.01.12" "plugin_name.zip" \
     --title "Plugin Name v1.0.0" \
     --notes "Release notes"
   ```

## 📞 支持

如有问题请：
1. 检查本指南的故障排除部分
2. 提交Issue: https://github.com/dysobo/NotifyHub_plugins/issues
3. 查看Actions日志获取详细错误信息

---

*最后更新: 2025年*
