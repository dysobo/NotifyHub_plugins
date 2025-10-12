# 插件管理器重启指南

## 🔄 重启NotifyHub服务

为了让左侧菜单显示"应用商店"入口，需要重启NotifyHub服务。

### 重启步骤

1. **停止NotifyHub服务**
   ```bash
   # 如果使用Docker
   docker stop notifyhub
   
   # 如果使用systemd
   sudo systemctl stop notifyhub
   
   # 如果直接运行
   # 找到NotifyHub进程并终止
   ```

2. **启动NotifyHub服务**
   ```bash
   # 如果使用Docker
   docker start notifyhub
   
   # 如果使用systemd
   sudo systemctl start notifyhub
   
   # 如果直接运行
   # 重新启动NotifyHub程序
   ```

3. **验证菜单显示**
   - 访问NotifyHub主页面
   - 检查左侧菜单是否出现"插件页面"分组
   - 确认"应用商店"入口是否显示

## 📋 修复内容

### 1. 删除默认仓库
- ✅ 移除了不存在的官方仓库和社区仓库
- ✅ 更新了manifest.json配置
- ✅ 现在只使用自定义仓库

### 2. 修复下载逻辑
- ✅ 添加了调试日志
- ✅ 修复了GitHub URL解析
- ✅ 改进了错误处理

### 3. 菜单配置
- ✅ manifest.json中已正确配置frontend_page
- ✅ add_to_menu设置为true
- ✅ 重启后应该显示在左侧菜单

## 🎯 预期结果

重启后您应该看到：

1. **左侧菜单**：
   - 插件页面
     - 📱 应用商店

2. **应用商店功能**：
   - 可以正常浏览插件
   - 可以正常安装插件
   - 支持GitHub仓库下载

## 🔍 如果仍有问题

如果重启后菜单仍然没有显示，请检查：

1. **插件状态**：确保插件管理器已启用
2. **配置保存**：确保插件配置已保存
3. **日志检查**：查看NotifyHub启动日志是否有错误
4. **文件权限**：确保插件文件有正确的读取权限

## 📞 技术支持

如果问题仍然存在，请提供：
- NotifyHub启动日志
- 插件管理器配置截图
- 浏览器控制台错误信息
