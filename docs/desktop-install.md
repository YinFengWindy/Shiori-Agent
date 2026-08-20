# Windows 安装与更新

Shiori 的 Windows 安装包面向 x64 Windows 11。安装和首次启动不需要 Node.js、npm、Python、uv 或 Git。

安装器采用当前用户安装方式。升级会替换程序和内置 runtime，但不会覆盖 `%USERPROFILE%\.shiori\workspace` 中的 `config.toml`、角色、会话、记忆、Story 或素材；卸载也不会删除这些用户数据。

首次启动会在 `%USERPROFILE%\.shiori\workspace\config.toml` 创建配置模板。填写模型配置后重启 bridge 即可生效。

首版安装包未使用 Authenticode 签名时，Windows SmartScreen 可能显示警告。仅应从项目的 GitHub Release 下载；确认发布者和 SHA-256 后，选择“更多信息”中的继续运行。后续签名接入不会改变安装或更新协议。

应用只在正式打包版本中从 GitHub Releases 检查更新。更新缓存、窗口状态和桌面日志位于 `%APPDATA%\Shiori`。

开发者在本机运行 `npm --prefix desktop run package:win` 时，构建产物默认写入 `%LOCALAPPDATA%\Shiori\release`。CI 通过 `SHIORI_RELEASE_OUTPUT` 显式写入仓库内的 artifact 目录。
