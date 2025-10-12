# 内置依赖说明

## 概述

此插件已内置所有必要的依赖包到 `vendor` 目录中，解决了依赖下载失败的问题。

## 内置依赖包

- `zhdate` - 农历日期转换
- `beautifulsoup4` - HTML解析
- `cryptography` - 加密库
- `pillow` - 图像处理
- `requests` - HTTP请求
- `PyJWT` - JWT令牌处理

## 工作原理

1. 插件启动时会自动检查 `vendor` 目录
2. 如果找到依赖包，会自动安装到 `deps` 目录
3. 将 `deps` 目录添加到 Python 路径中
4. 正常导入和使用依赖包

## 文件结构

```
daily_news/
├── vendor/           # 内置依赖包目录
│   ├── zhdate-0.1-py3-none-any.whl
│   ├── beautifulsoup4-4.14.2-py3-none-any.whl
│   ├── cryptography-46.0.2-cp311-abi3-win_amd64.whl
│   ├── pillow-11.3.0-cp312-cp312-win_amd64.whl
│   ├── requests-2.32.5-py3-none-any.whl
│   └── PyJWT-2.10.1-py3-none-any.whl
├── deps/             # 自动生成的依赖安装目录
├── daily_news.py     # 主程序文件
└── requirements.txt  # 依赖说明文件
```

## 优势

- ✅ 无需网络连接即可安装依赖
- ✅ 避免依赖下载失败问题
- ✅ 版本固定，避免兼容性问题
- ✅ 插件开箱即用

## 注意事项

- `vendor` 目录中的依赖包是预下载的，请勿删除
- `deps` 目录是自动生成的，可以删除（插件会重新创建）
- 如果遇到问题，可以删除 `deps` 目录让插件重新安装依赖
