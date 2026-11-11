# pet_codex_sprite

Codex 精灵图形象提供者，依赖 `desktop_pet` 和 SDK 4.1.1。桌宠管理角色、气泡、语音和直播；本插件管理精灵包、图集渲染和自己的透明窗口。

## 使用

启用桌宠和 Codex 精灵图插件，在角色素材库导入 ZIP 并选择模型，然后启用该角色的桌宠。ZIP 沿用 `pet.json`、`spritesheetPath` 和可选 `previewPath/actions` 格式；尺寸、图集行和动作校验沿用原桌宠契约。

素材文件保存到 `plugin-data/pet_codex_sprite/pets-<role_id>/<package_id>/`。升级时自动迁移旧桌宠包及选择，无需重新导入；文件复制或元数据写入失败保留来源，修复后可重试。精灵插件停用不删除桌宠保存的模型引用。

## 生命周期

服务契约为 `shiori.pet-models.v1`，服务 ID 为 `models`。后端先检查 background 就绪再接受呈现请求，background 在图片真正加载后回报桌宠。surface 以隐藏状态准备，桌宠决定交接；切换、关闭及崩溃按实例身份释放资源。

本插件不建立 TTS 或直播队列，不依赖其它形象插件。公共视图和交互使用桌宠导出的 `@shiori-plugin/desktop_pet/provider`，精灵动作行名仅在本插件解释。

独立 Python 安装需同时提供 `shiori-plugin-desktop-pet>=0.1.4`；参见 `TESTING.md`。前端打包时把桌宠的 provider 导出打入插件，React 和 Shiori SDK 保持宿主 peer。
