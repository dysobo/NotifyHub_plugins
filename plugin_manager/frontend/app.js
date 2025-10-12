const { createApp } = Vue;
const { createVuetify } = Vuetify;

const vuetify = createVuetify({
    theme: {
        defaultTheme: 'light',
        themes: {
            light: {
                colors: {
                    primary: '#1976D2',      // 保持NotifyHub主色调
                    secondary: '#424242',    // 中性灰色
                    accent: '#1976D2',       // 与主色保持一致
                    error: '#F44336',        // 标准错误色
                    info: '#2196F3',         // 信息蓝色
                    success: '#4CAF50',      // 成功绿色
                    warning: '#FF9800',      // 警告橙色
                    background: '#FAFAFA',   // 浅灰背景
                    surface: '#FFFFFF'       // 白色表面
                }
            }
        }
    }
});

createApp({
    data() {
        return {
            // 基本状态
            loading: false,
            activeTab: 'market',
            
            // 筛选（保留仓库筛选用于后端）
            selectedRepository: null,
            
            // 数据
            marketPlugins: [],
            installedPlugins: [],
            repositories: [],
            pluginBackups: [],
            
            // 统计信息
            stats: {
                totalPlugins: 0,
                installedPlugins: 0,
                repositories: 0,
                updatesAvailable: 0
            },
            
            // 对话框状态
            showSettings: false,
            showPluginDetails: false,
            showAddRepository: false,
            
            // 选中的项目
            selectedPlugin: null,
            selectedPluginForBackup: null,
            installingPlugins: [],
            refreshingRepos: [],
            
            // 表单数据
            settings: {
                proxy_enabled: false,
                proxy_url: '',
                custom_repository_urls: '',
                auto_check_updates: true,
                backup_retention_days: '30'
            },
            newRepository: {
                id: '',
                name: '',
                url: '',
                description: ''
            },
            repositoryFormValid: false,
            
            // 表格配置
            installedHeaders: [
                { title: '图标', key: 'logo', sortable: false },
                { title: '插件名称', key: 'name' },
                { title: '版本', key: 'version' },
                { title: '作者', key: 'author' },
                { title: '最后修改', key: 'last_modified' },
                { title: '操作', key: 'actions', sortable: false }
            ],
            backupHeaders: [
                { title: '备份文件', key: 'filename' },
                { title: '大小', key: 'size' },
                { title: '创建时间', key: 'created' },
                { title: '操作', key: 'actions', sortable: false }
            ]
        };
    },
    
    computed: {
        repositoryOptions() {
            return this.repositories
                .filter(repo => repo.enabled)
                .map(repo => ({
                    title: repo.name,
                    value: repo.id
                }));
        },
        
    },
    
    mounted() {
        this.initializeApp();
    },
    
    watch: {
        selectedPluginForBackup(newPlugin) {
            if (newPlugin) {
                this.loadPluginBackups(newPlugin.id);
            }
        }
    },
    
    methods: {
        async initializeApp() {
            this.loading = true;
            try {
                await Promise.all([
                    this.loadSettings(),
                    this.loadRepositories(),
                    this.loadInstalledPlugins(),
                    this.loadStats()
                ]);
                
                // 默认加载市场插件
                await this.loadMarketPlugins();
            } catch (error) {
                this.showError('初始化失败: ' + error.message);
            } finally {
                this.loading = false;
            }
        },
        
        async loadSettings() {
            try {
                const response = await this.apiRequest('/status');
                this.settings = {
                    proxy_enabled: response.proxy_enabled,
                    proxy_url: response.proxy_url,
                    custom_repository_urls: response.custom_repository_urls || '',
                    auto_check_updates: response.auto_check_updates,
                    backup_retention_days: response.backup_retention_days
                };
            } catch (error) {
                console.error('加载设置失败:', error);
            }
        },
        
        async loadRepositories() {
            try {
                const response = await this.apiRequest('/repositories');
                this.repositories = response.repositories;
            } catch (error) {
                console.error('加载仓库失败:', error);
            }
        },
        
        async loadMarketPlugins() {
            try {
                const params = new URLSearchParams();
                if (this.selectedRepository) params.append('repository_id', this.selectedRepository);
                
                const response = await this.apiRequest('/plugins/search?' + params.toString());
                this.marketPlugins = response.plugins;
                
                // 显示仓库连接状态
                if (response.failed_repositories && response.failed_repositories.length > 0) {
                    console.warn('部分仓库连接失败:', response.failed_repositories);
                    this.showWarning(`部分仓库连接失败: ${response.failed_repositories.join(', ')}`);
                }
                
                console.log(`加载完成: 找到 ${response.plugins.length} 个插件，成功连接 ${response.successful_repositories}/${response.total_repositories} 个仓库`);
            } catch (error) {
                console.error('加载市场插件失败:', error);
                this.showError('加载插件列表失败: ' + error.message);
            }
        },
        
        async loadInstalledPlugins() {
            try {
                const response = await this.apiRequest('/installed');
                this.installedPlugins = response.plugins;
            } catch (error) {
                console.error('加载已安装插件失败:', error);
            }
        },
        
        async loadStats() {
            try {
                const response = await this.apiRequest('/status');
                this.stats = {
                    totalPlugins: this.marketPlugins.length,
                    installedPlugins: this.installedPlugins.length,
                    repositories: response.repositories_count,
                    updatesAvailable: this.marketPlugins.filter(p => p.can_update).length
                };
            } catch (error) {
                console.error('加载统计信息失败:', error);
            }
        },
        
        async loadPluginBackups(pluginId) {
            try {
                console.log('正在加载插件备份列表:', pluginId);
                const response = await this.apiRequest(`/backups?plugin_id=${pluginId}`);
                console.log('备份列表响应:', response);
                this.pluginBackups = response.backups || [];
                console.log('设置备份列表:', this.pluginBackups);
            } catch (error) {
                console.error('加载备份列表失败:', error);
                this.pluginBackups = [];
            }
        },
        
        
        async installPlugin(plugin) {
            if (this.installingPlugins.includes(plugin.id)) return;
            
            this.installingPlugins.push(plugin.id);
            try {
                await this.apiRequest('/plugins/install', {
                    method: 'POST',
                    body: JSON.stringify({
                        plugin_id: plugin.id,
                        repository_id: plugin.repository_id
                    })
                });
                
                this.showSuccess(`开始安装插件 "${plugin.name}"`);
                
                // 更新插件状态
                plugin.installed = true;
                await this.loadInstalledPlugins();
                this.loadStats();
                
            } catch (error) {
                this.showError('安装插件失败: ' + error.message);
            } finally {
                this.installingPlugins = this.installingPlugins.filter(id => id !== plugin.id);
            }
        },
        
        async updatePlugin(plugin) {
            await this.installPlugin(plugin);
        },
        
        async uninstallPlugin(plugin) {
            if (!confirm(`确定要卸载插件 "${plugin.name}" 吗？`)) return;
            
            try {
                await this.apiRequest(`/plugins/${plugin.id}`, { method: 'DELETE' });
                this.showSuccess(`插件 "${plugin.name}" 卸载成功`);
                
                // 更新数据
                await this.loadInstalledPlugins();
                this.loadMarketPlugins();
                this.loadStats();
                
            } catch (error) {
                this.showError('卸载插件失败: ' + error.message);
            }
        },
        
        viewPluginDetails(plugin) {
            this.selectedPlugin = plugin;
            this.showPluginDetails = true;
        },
        
        async addRepository() {
            try {
                await this.apiRequest('/repositories', {
                    method: 'POST',
                    body: JSON.stringify(this.newRepository)
                });
                
                this.showSuccess('仓库添加成功');
                this.showAddRepository = false;
                this.newRepository = { id: '', name: '', url: '', description: '' };
                await this.loadRepositories();
                
            } catch (error) {
                this.showError('添加仓库失败: ' + error.message);
            }
        },
        
        async updateRepository(repo) {
            try {
                await this.apiRequest(`/repositories/${repo.id}`, {
                    method: 'PUT',
                    body: JSON.stringify(repo)
                });
                
                this.showSuccess('仓库更新成功');
                
            } catch (error) {
                this.showError('更新仓库失败: ' + error.message);
                // 恢复原状态
                repo.enabled = !repo.enabled;
            }
        },
        
        async deleteRepository(repo) {
            if (!confirm(`确定要删除仓库 "${repo.name}" 吗？`)) return;
            
            try {
                await this.apiRequest(`/repositories/${repo.id}`, { method: 'DELETE' });
                this.showSuccess('仓库删除成功');
                await this.loadRepositories();
                
            } catch (error) {
                this.showError('删除仓库失败: ' + error.message);
            }
        },
        
        editRepository(repo) {
            this.newRepository = { ...repo };
            this.showAddRepository = true;
        },
        
        async createBackup() {
            if (!this.selectedPluginForBackup) return;
            
            try {
                await this.apiRequest('/backups', {
                    method: 'POST',
                    body: JSON.stringify({
                        plugin_id: this.selectedPluginForBackup.id,
                        backup_name: `${this.selectedPluginForBackup.name}_backup`
                    })
                });
                
                this.showSuccess('备份创建成功');
                await this.loadPluginBackups(this.selectedPluginForBackup.id);
                
            } catch (error) {
                this.showError('创建备份失败: ' + error.message);
            }
        },
        
        async restoreBackup(backup) {
            if (!confirm(`确定要恢复备份 "${backup.filename}" 吗？这将覆盖当前插件文件。`)) return;
            
            try {
                await this.apiRequest('/backups/restore', {
                    method: 'POST',
                    body: JSON.stringify({
                        plugin_id: this.selectedPluginForBackup.id,
                        backup_file: backup.filename
                    })
                });
                
                this.showSuccess('备份恢复成功');
                await this.loadInstalledPlugins();
                
            } catch (error) {
                this.showError('恢复备份失败: ' + error.message);
            }
        },
        
        async deleteBackup(backup) {
            if (!confirm(`确定要删除备份 "${backup.filename}" 吗？`)) return;
            
            try {
                await this.apiRequest(`/backups/${this.selectedPluginForBackup.id}/${backup.filename}`, {
                    method: 'DELETE'
                });
                
                this.showSuccess('备份删除成功');
                await this.loadPluginBackups(this.selectedPluginForBackup.id);
                
            } catch (error) {
                this.showError('删除备份失败: ' + error.message);
            }
        },
        
        manageBackups(plugin) {
            this.selectedPluginForBackup = plugin;
            this.activeTab = 'backups';
        },
        
        async saveSettings() {
            try {
                await this.apiRequest('/settings', {
                    method: 'POST',
                    body: JSON.stringify(this.settings)
                });
                
                this.showSuccess('设置保存成功');
                this.showSettings = false;
                
                // 重新加载数据以应用新设置
                await this.loadRepositories();
                await this.loadMarketPlugins();
                
            } catch (error) {
                this.showError('保存设置失败: ' + error.message);
            }
        },
        
        async refreshData() {
            await this.initializeApp();
            this.showSuccess('数据刷新成功');
        },
        
        async testRepository(repo) {
            try {
                this.showInfo(`正在测试仓库 "${repo.name}" 的连接...`);
                
                const response = await this.apiRequest(`/repositories/${repo.id}/plugins`);
                
                if (response.plugins && response.plugins.length > 0) {
                    this.showSuccess(`仓库 "${repo.name}" 连接成功，找到 ${response.plugins.length} 个插件`);
                } else {
                    this.showWarning(`仓库 "${repo.name}" 连接成功，但没有找到插件`);
                }
                
                // 重新加载插件列表
                await this.loadMarketPlugins();
                
            } catch (error) {
                this.showError(`仓库 "${repo.name}" 连接失败: ${error.message}`);
            }
        },
        
        async refreshRepository(repo) {
            if (this.refreshingRepos.includes(repo.id)) return;
            
            this.refreshingRepos.push(repo.id);
            try {
                this.showInfo(`正在刷新仓库 "${repo.name}"...`);
                
                const response = await this.apiRequest(`/repositories/${repo.id}/refresh`, {
                    method: 'POST'
                });
                
                this.showSuccess(`仓库 "${repo.name}" 刷新成功，找到 ${response.plugins_count} 个插件`);
                
                // 重新加载数据
                await this.loadMarketPlugins();
                await this.loadRepositories();
                
            } catch (error) {
                this.showError(`刷新仓库 "${repo.name}" 失败: ${error.message}`);
            } finally {
                this.refreshingRepos = this.refreshingRepos.filter(id => id !== repo.id);
            }
        },
        
        // 工具方法
        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        },
        
        formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        },
        
        async apiRequest(endpoint, options = {}) {
            const url = `/api/plugins/plugin_manager${endpoint}`;
            const config = {
                headers: {
                    'Content-Type': 'application/json'
                },
                ...options
            };
            
            const response = await fetch(url, config);
            
            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: '请求失败' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }
            
            return await response.json();
        },
        
        getRepositoryName(repositoryId) {
            const repo = this.repositories.find(r => r.id === repositoryId);
            return repo ? repo.name : repositoryId;
        },
        
        getRepositoryColor(repositoryId) {
            const colors = ['primary', 'secondary', 'success', 'warning', 'info', 'error'];
            const index = this.repositories.findIndex(r => r.id === repositoryId);
            return colors[index % colors.length];
        },
        
        isDefaultRepository(repositoryId) {
            return ['official', 'community'].includes(repositoryId);
        },
        
        getRepositoryType(repositoryId) {
            if (['official', 'community'].includes(repositoryId)) {
                return repositoryId === 'official' ? '官方' : '社区';
            } else if (repositoryId.startsWith('custom_')) {
                return '自定义';
            } else {
                return '手动';
            }
        },
        
        getRepositoryTypeColor(repositoryId) {
            if (['official', 'community'].includes(repositoryId)) {
                return repositoryId === 'official' ? 'primary' : 'secondary';
            } else if (repositoryId.startsWith('custom_')) {
                return 'success';
            } else {
                return 'info';
            }
        },
        
        formatFileSize(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        },
        
        formatDate(dateString) {
            return new Date(dateString).toLocaleString('zh-CN');
        },
        
        showSuccess(message) {
            // 这里可以使用Vuetify的snackbar组件
            console.log('Success:', message);
        },
        
        showError(message) {
            // 这里可以使用Vuetify的snackbar组件
            console.error('Error:', message);
            alert('错误: ' + message); // 临时使用alert
        },
        
        showWarning(message) {
            // 这里可以使用Vuetify的snackbar组件
            console.warn('Warning:', message);
            alert('警告: ' + message); // 临时使用alert
        },
        
        showInfo(message) {
            // 这里可以使用Vuetify的snackbar组件
            console.info('Info:', message);
            alert('信息: ' + message); // 临时使用alert
        },
        
        debounce(func, wait) {
            clearTimeout(this.debounceTimer);
            this.debounceTimer = setTimeout(func, wait);
        }
    }
}).use(vuetify).mount('#app');
