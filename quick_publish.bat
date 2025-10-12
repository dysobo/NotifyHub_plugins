@echo off
chcp 65001 >nul
echo NotifyHub 插件快速发布工具
echo ================================

echo.
echo 当前可用的发布方式:
echo 1. 使用GitHub Actions自动发布 (推荐)
echo 2. 使用Python脚本发布 (需要GitHub Token)
echo 3. 查看当前插件包状态
echo.

set /p choice="请选择发布方式 (1/2/3): "

if "%choice%"=="1" (
    echo.
    echo 正在打开GitHub Actions页面...
    echo 请在网页中:
    echo 1. 点击 "Run workflow" 按钮
    echo 2. 勾选 "确认发布所有插件包"
    echo 3. 点击 "Run workflow" 确认
    echo.
    start https://github.com/dysobo/NotifyHub_plugins/actions/workflows/publish-all-plugins.yml
    echo GitHub Actions页面已打开
    goto end
)

if "%choice%"=="2" (
    echo.
    echo 使用Python脚本发布...
    echo 注意: 需要设置GITHUB_TOKEN环境变量
    echo.
    set /p token="请输入GitHub Token: "
    if "%token%"=="" (
        echo 错误: 需要提供GitHub Token
        goto end
    )
    set GITHUB_TOKEN=%token%
    python publish_packages.py
    goto end
)

if "%choice%"=="3" (
    echo.
    echo 当前插件包状态:
    echo.
    if exist packages\*.zip (
        for %%f in (packages\*.zip) do (
            echo   - %%~nxf
        )
        echo.
        echo 插件包总数:
        dir packages\*.zip /b | find /c /v ""
    ) else (
        echo   [无插件包] 请先运行 python package_plugins.py
    )
    goto end
)

echo 无效选择
goto end

:end
echo.
pause
